# Bracket (Ctrl-Alt-GG fork)

Tournament system used by the Ctrl-Alt-GG LAN community, hosted at
<https://bracket.ctrl-alt-gg.hu>.

This is a fork of [evroon/bracket](https://github.com/evroon/bracket). It tracks
upstream loosely, but the deployment, configuration defaults, and frontend
delivery have diverged, so upstream docs do not always apply here. Changes are
made for our own event, not as a general-purpose distribution.

## Layout

| Path | What it is |
| --- | --- |
| `backend/` | FastAPI application, Alembic migrations, `cli.py`, pytest suite |
| `frontend/` | React 19 + Vite SPA, served in production by nginx |
| `docker-compose.yml` | The production stack (backend, frontend, PostgreSQL, Redis) |
| `.github/workflows/static-checks.yml` | Lint, type checks and tests of both parts, on every push |
| `.github/workflows/publish.yml` | Runs the checks, then builds and pushes images to GHCR on `v*` tags |

## Deployment

Images come from GHCR and are built by the publish workflow whenever a `v*` tag
is pushed. It runs the checks first and publishes nothing when they fail:

```
ghcr.io/ctrl-alt-gg/bracket-backend:<tag>
ghcr.io/ctrl-alt-gg/bracket-frontend:<tag>
```

Compose requires these values in the environment before `docker compose up`,
`APP_IMAGE_TAG` being the tag of the release to run:

```bash
APP_IMAGE_TAG=... POSTGRES_DB=... POSTGRES_USER=... POSTGRES_PASSWORD=... JWT_SECRET=... \
  docker compose up -d
```

Both application containers run read-only, without Linux capabilities and
without a way to gain privileges. The backend writes only to the uploads volume
and `/tmp`, the frontend's nginx only to `/tmp` and its rendered configuration.
The backend runs four worker processes by default (`WEB_CONCURRENCY`), so a long
request doesn't hold up the others.

On startup the backend connects to the database, runs Alembic migrations
(`AUTO_RUN_MIGRATIONS`, on by default), and — if the database is empty and
`ADMIN_EMAIL`/`ADMIN_PASSWORD` are set — creates the initial admin user.
Health check: `GET /api/ping`. Uploaded logos are kept in the `bracket_uploads`
volume.

Upgrades validate existing tournament relationships and point values before changing
the schema. If an upgrade reports incompatible rows, correct the listed records in
the previous application version or database, then retry. Keep the reported migration
pending until those corrections are complete.

Logo uploads are limited to 4 megapixels and 4096 pixels per side before decoding,
then reduced to 512 pixels and stripped of image metadata.

### Accounts

Signing up is off (`ALLOW_USER_REGISTRATION`). Every open tournament is public
and listed on the home page, so with signup on, anyone can publish there.
Organizers get their account from the command line, in the backend container:

```bash
docker exec -it bracket-backend python cli.py register-user   # asks for email, name and password
docker exec -it bracket-backend python cli.py set-password    # a forgotten password
docker exec -it bracket-backend python cli.py clear-user-lock --email someone@example.org
```

- **Sharing an event.** The owner of an event adds other accounts on the Events
  page, by email. They can manage its tournaments; only the owner renames or
  deletes the event and decides who helps. Nobody needs to share a login. An
  owner who leaves the organizing team makes another organizer the owner there.
- **An event without a reachable owner.** When the owner's account is gone or
  they can't sign in, `docker exec -it bracket-backend python cli.py
  set-event-owner` makes another account the owner (it asks for the event's
  name or id and the account's email).
- **Failed logins.** Five wrong passwords lock an account for fifteen minutes,
  but only for the client address they came from. Someone guessing from
  elsewhere doesn't lock the organizer out. `clear-user-lock` lifts a lock
  early; without `--address` it asks for the address that is locked.
- **A forgotten password.** There is no email reset. `set-password` sets a new
  one and signs the account out everywhere.

### Reverse proxy

Both containers listen on `127.0.0.1` only; a reverse proxy on the host
terminates TLS and routes `/api` to the backend (port 8400) and everything else
to the frontend (port 3000).

- **Client addresses.** Login and registration are rate limited per client IP,
  and failed logins lock an account for one address only. The backend only
  trusts `X-Forwarded-For` from the addresses in `FORWARDED_ALLOW_IPS`;
  otherwise every request seems to come from the proxy, all visitors share one
  limit, and anyone could lock an organizer out. Docker forwards the published
  ports from the network's gateway, so that is the default: `172.31.240.1`, on
  the fixed `172.31.240.0/24` subnet that `docker-compose.yml` gives the
  network. If that subnet is taken on the host, change it there and set
  `FORWARDED_ALLOW_IPS` to its gateway. The backend logs a warning when a
  request carries `X-Forwarded-For` from an address it doesn't trust.

  Don't use `*`: uvicorn then takes the left-most `X-Forwarded-For` entry, which
  the client chooses.
- **Request size.** Limit request bodies at the proxy (for example nginx's
  `client_max_body_size 4m`); logos are at most `UPLOAD_MAX_BYTES`.

## Configuration

Read from the environment by `backend/bracket/config.py`. `ENVIRONMENT` selects
the `PRODUCTION` or `DEVELOPMENT` config class, which picks up `prod.env` or
`dev.env` respectively.

| Variable | Notes |
| --- | --- |
| `ENVIRONMENT` | `PRODUCTION` (the default) / `DEVELOPMENT`. Development serves the API docs, sends no security headers and sets a cookie that works over plain HTTP, so it has to be asked for |
| `JWT_SECRET` | Required. Startup fails below 32 characters |
| `PG_DSN` | PostgreSQL connection string |
| `BASE_URL` | Public URL; also the default JWT issuer |
| `API_PREFIX` | `/api` in our deployment; affects every route and the static mount |
| `CORS_ORIGINS` | Comma-separated allowlist. `*` is rejected |
| `CORS_ALLOW_CREDENTIALS` | Only for a frontend on another origin (see Sessions) |
| `RATE_LIMIT_STORAGE_URI` | Must not be `memory://` in production (see below) |
| `ALLOW_USER_REGISTRATION` | Self-service signup. Off unless set (see Accounts) |
| `ADMIN_EMAIL` / `ADMIN_PASSWORD` | Only used to bootstrap an empty database |
| `ACCESS_TOKEN_EXPIRE_MINUTES` | How long a session lasts without being used. 720 (12 hours) by default, minimum 5 |
| `UPLOAD_DIR` / `UPLOAD_MAX_BYTES` | Team and tournament logo uploads |
| `FORWARDED_ALLOW_IPS` | The reverse proxy's address (see above); read by uvicorn |
| `WEB_CONCURRENCY` | Backend worker processes, 4 in the image; read by uvicorn |

## Local development

Backend (needs [uv](https://docs.astral.sh/uv/) and a PostgreSQL instance):

```bash
cd backend
uv sync
uv run ./cli.py create-dev-db     # seeds a database with dummy data
API_PREFIX=/api uv run uvicorn bracket.app:app --reload --port 8400
```

Set `ENVIRONMENT=DEVELOPMENT` for all of these; without it the backend runs as
in production. `DevelopmentConfig` reads `backend/dev.env`, which is not
committed. At minimum it needs `JWT_SECRET` and `PG_DSN`. The interactive API
docs (`/docs`, `/redoc`) are only served in development.

Database entities live in `backend/bracket/orm/`. Repository functions in `bracket/sql/`
use an `AsyncSession` and return the Pydantic models in `bracket/models/db/` that define
the API contract. GET, HEAD and OPTIONS requests use read-only `REPEATABLE READ`
transactions, so loaded graphs, standings and totals share a database snapshot. Commands
use `READ COMMITTED` and commit before the response is sent. Tournament edits lock the
tournament before changing results or competitors; membership edits lock the event before
checking access. Relationships require explicit eager loading.

The cached Details loader owns its snapshot transaction. Its authorization check releases
its connection before waiting for that loader, so requests waiting on the cache do not
hold another database connection.

Ranking rules and stage-slot points use PostgreSQL `NUMERIC` and Python `Decimal`, with
six decimal places. Rule values range from -1000 to 1000; requests with greater decimal
precision are rejected.

Tests need a disposable PostgreSQL database. Migration tests also need a database role
with permission to create databases. They restore the frozen `b2e5c8d1f4a7` schema in
`backend/tests/migration_tests/assets/`, upgrade populated data to head, exercise downgrade
and re-upgrade, and compare the resulting schema with ORM metadata, including defaults.
They test empty-database bootstrap separately. CI runs these checks before the unit and
integration suite, whose fixtures create tables from metadata.

```bash
cd backend
ENVIRONMENT=DEVELOPMENT JWT_SECRET=... PG_DSN=... uv run pytest tests/migration_tests
ENVIRONMENT=DEVELOPMENT JWT_SECRET=... PG_DSN=... uv run alembic stamp head
ENVIRONMENT=DEVELOPMENT JWT_SECRET=... PG_DSN=... uv run pytest tests/unit_tests tests/integration_tests
```

Stamping the integration-test database keeps startup from replaying migrations over
fixture-created tables. Existing installations at `b2e5c8d1f4a7` upgrade through Alembic
normally. An empty installation uses startup bootstrap because the oldest historical
migrations assume application tables already exist. After changing entities, add the
corresponding migration and run the migration suite; `alembic check` against a migrated
database checks for remaining schema differences.

Frontend:

```bash
cd frontend
corepack enable
pnpm install
pnpm dev     # on localhost; `pnpm dev --host` makes it reachable from other devices
pnpm test    # type check, lint (oxlint), formatting (oxfmt) and unit tests (vitest)
pnpm exec playwright install chromium
pnpm test:browser  # organizer workflows, concurrency, refresh failures and logout recovery
```

The dev server forwards `/api` to the backend on port 8400, so the page and the
API share an origin, as they do in production.

After changing the API, run `uv run python cli.py generate-openapi` in `backend/`
and `pnpm openapi-ts` in `frontend/`. The export uses `/api` by default even when
the local backend's `API_PREFIX` is empty, keeping generated client names stable.

The SPA resolves its API base URL from `window.__BRACKET_RUNTIME_CONFIG__`
(injected by the container entrypoint from `API_BASE_URL`), then
`VITE_API_BASE_URL`, and otherwise uses its own origin. Leave `API_BASE_URL`
empty when the reverse proxy serves both from one origin. Otherwise set it to
the backend **origin only** — the client appends `/api/...` itself, so a
trailing `/api` or `/` is stripped before use.

### Sessions

Logging in sets an HttpOnly session cookie, so scripts on the page can't read
the token; API clients can still send it as a bearer token. The cookie is
`SameSite=Strict`, so the API must be on the same site as the frontend (for
example the same domain). If it is on another origin of that site, also set
`CORS_ALLOW_CREDENTIALS=true` next to `CORS_ORIGINS`. Requests that change
something with the cookie need an `X-Requested-With: XMLHttpRequest` header,
which other sites can't send (CSRF protection). Logging in from another site is
refused as well, so nobody can be signed in to an account they didn't choose.

A session lasts `ACCESS_TOKEN_EXPIRE_MINUTES` from when it was last used: the
cookie is renewed while the organizer works, so an event day doesn't end with a
login form. Logging out ends the session on the server too, including for a
copy of its token. Changing the password signs out every other session.

A request without a valid session answers 401, and the page asks to log in
again. A valid session that may not do something answers 403 and stays signed
in.

### Organizer edits

Recorded results stay with the teams that played them. Before replacing a team
in a stage slot, clear that team's affected results in Rounds by saving 0-0 as
not played. Clearing a knockout result also clears the dependent results whose
competitors change. Other teams' results are kept.

Regenerating Swiss pairings replaces the draft in one operation. Its name and
round stay the same, and a failure keeps the original pairings. Return a published
round to draft before regenerating it, and clear any draft results first.

Team totals count published, played matches across the tournament. They follow
corrections, cleared scores and removed rounds; unpublished draft results do not
count. Stage standings continue to use each stage item's own ranking rules.

Teams with the same points are ranked by their matches against each other, then
by score difference, total score and wins. Teams that are level on all of these
keep the order of their slots. The stage editor shows where that order alone
decides who moves on, before the next stage is activated.

### Public pages

`GET /api/tournaments/{id}/details` returns everything the Details pages show in
one response, which the backend keeps for a few seconds. A venue full of phones
that refresh every half minute shares one Details load per tournament every few
seconds. Each load uses several database queries.

The other public reads of a tournament (stages, players, teams, rankings and
standings) are worked out on every request. A client that can't manage the
tournament gets 60 of those a minute per address; its organizers have no limit.
