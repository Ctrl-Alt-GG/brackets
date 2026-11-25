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

- **Sharing a tournament.** The owner of a tournament adds other accounts in
  its Settings, by email. They can manage the tournament; only the owner decides
  who helps, hands the tournament over and deletes it. Nobody needs to share a
  login. An owner who leaves the organizing team makes another organizer the
  owner there.
- **A tournament without a reachable owner.** When the owner's account is gone
  or they can't sign in, `docker exec -it bracket-backend python cli.py
  set-tournament-owner` makes another account the owner (it asks for the
  tournament's name or id and the account's email). The previous owner stays
  on as an organizer.
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
the API contract; enums and result values shared by both are in `bracket/models/`.
Commands, and the answers that combine stored data with results replayed from the
matches, are functions in `bracket/logic/`, which routes in `bracket/routes/` call once
they have checked who asks. A command that changes the loaded stage tree does so through
`TournamentGraph`, which keeps the copies of a slot in its stage item and in its matches
in agreement. Relationships require explicit eager loading.

GET, HEAD and OPTIONS requests use read-only `REPEATABLE READ` transactions, so loaded
graphs, standings and totals share a database snapshot. Commands use `READ COMMITTED` and
commit before the response is sent. A tournament command locks the tournament before it
checks access, so someone who loses access loses it once the commands already let in have
finished; changing who runs a tournament is such a command too. Commands that make lineups
follow rosters lock tournaments before teams: adding teams to a tournament or reopening it
locks those teams against changes. A roster change is the exception: it locks the team, then
the team's open tournaments by id. `bracket/logic/participation.py` explains why that can't
deadlock. Creating a tournament locks the account, so that two creations can't both take the
last place its limit of owned tournaments allows. A logo stored for a command is removed
again unless the command commits.

The cached Details loader owns its snapshot transaction. Its authorization check releases
its connection before waiting for that loader, so requests waiting on the cache do not
hold another database connection.

Ranking rules and stage-slot points use PostgreSQL `NUMERIC` and Python `Decimal`, with
six decimal places. Rule values range from -1000 to 1000; requests with greater decimal
precision are rejected.

Tests need a PostgreSQL server and a database role that may create databases. They never
change the database `PG_DSN` names: the integration tests create one of their own (one per
worker with `pytest -n`), with tables from the metadata stamped at the latest migration, and
drop it afterwards; their uploads go to a temporary directory. Migration tests likewise
create a database per test. They restore the frozen `b2e5c8d1f4a7` schema in
`backend/tests/migration_tests/assets/`, upgrade populated data to head, exercise downgrade
and re-upgrade, and compare the resulting schema with ORM metadata, including defaults.
They test empty-database bootstrap separately. CI runs these checks before the unit and
integration suite.

```bash
cd backend
ENVIRONMENT=DEVELOPMENT JWT_SECRET=... PG_DSN=... uv run pytest tests/migration_tests
ENVIRONMENT=DEVELOPMENT JWT_SECRET=... PG_DSN=... uv run pytest tests/unit_tests tests/integration_tests
```

Existing installations at `b2e5c8d1f4a7` upgrade through Alembic normally. An empty installation uses startup bootstrap because the oldest historical
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
pnpm test:smoke    # against the real API, see below
pnpm test:image    # against the production image, see below
```

The browser regressions answer the page's API requests themselves. Two smaller
suites check the boundaries those answers stand in for:

- `test:smoke` starts the API (with `uv`) and the dev server, and runs login,
  ranking editing, score entry and logout against them. It needs `PG_DSN`,
  naming a database of its own that the API sets up when it is empty, and
  `JWT_SECRET`.
- `test:image` checks the production image: the runtime configuration, the
  Content-Security-Policy, deep links, caching and a bracket. Start the image
  with `API_BASE_URL` set to its own address, and point `BRACKET_IMAGE_URL` at
  it (by default `http://127.0.0.1:8080`).

The dev server forwards `/api` to the backend on port 8400, so the page and the
API share an origin, as they do in production.

After changing the API, run `uv run python cli.py generate-openapi` in `backend/`
and `pnpm openapi-ts` in `frontend/`. The export uses `/api` by default even when
the local backend's `API_PREFIX` is empty, keeping generated client names stable.

The frontend container reads the API's address from `API_BASE_URL` when it
starts. Leave it empty when the reverse proxy serves both from one origin.
Otherwise set it to the backend's **origin only**, such as
`https://api.example.org`: the client adds `/api/...` itself. The container
refuses to start with anything else, such as a value with a path or a trailing
`/`. The page and its Content-Security-Policy both use the checked value.

### API

Everything the frontend does goes through the API, so scripts and other tools can do the same.
`backend/openapi/openapi.json` describes every route and model, and a unit test fails when it falls
behind the code. Production serves neither this description nor the interactive docs: open the
file in an OpenAPI viewer, or open `http://127.0.0.1:8400/docs` while the development backend runs.

A script logs in with `POST /api/token`, sending the email as `username` and the `password` as form
fields. The answer's `access_token` is the session; send it as `Authorization: Bearer <token>`, and
reuse it, because logins are rate limited. The frontend gets a cookie instead (see Sessions).
Messages are in English, or in Hungarian for a request with `Accept-Language: hu`.

### Languages

Every page, and every message of the API, is in Hungarian and English. The page uses the language
chosen with its switch, or else the browser's, and asks the API for the same with
`Accept-Language`.

- The frontend's texts are in `frontend/src/app/locales.ts`, for the pages everyone opens, and in
  `frontend/src/app/organizer-locales.ts`, which loads with the organizer pages only.
- The API writes its messages in English, through `gettext` and `ngettext` from
  `bracket/utils/i18n.py`. Their Hungarian texts are in
  `backend/bracket/locale/hu/LC_MESSAGES/messages.po`, which the API reads when it starts. A unit
  test fails when a message has no Hungarian text there, or the catalog has one nothing uses.
- The API stores English names for what it names itself: rounds ("Round 01"), a new stage
  ("Stage") and a stage item created without a name (its format). Pages and messages show these in
  their own language; a name an organizer typed stays as it is.

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

### Teams and players

Teams and players don't belong to a tournament. Every organizer shares them on the Teams and
players page, and a team can take part in several tournaments at once. A tournament's lineup is
the active members of its teams; inactive members stay in the roster without playing. A player
can be an active member of only one of a tournament's teams, so a roster change or a joining
team that would make someone play for two of them is refused, with the player's name. Roster
changes reach the lineups of open tournaments. An archived tournament keeps the lineup it was
played with, and reopening it takes the current rosters again, unless they break that rule.

Match times avoid the other tournaments: a match starts once its teams and the players of their
lineups are free from the matches of other open tournaments. A tournament's times are planned
again when its matches change, its stages are activated, its knockout results come in, a roster
of its teams changes or it is reopened. Matches that still clash, for example because two
tournaments were planned at the same moment, are listed in the organizer view of the Schedule,
where Recalculate times plans the tournament again.

Team logos are public, since a team appears on the Details pages of every tournament it plays in.

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
