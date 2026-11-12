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

Compose requires these values in the environment before `docker compose up`:

```bash
POSTGRES_DB=... POSTGRES_USER=... POSTGRES_PASSWORD=... JWT_SECRET=... \
  docker compose up -d
```

On startup the backend connects to the database, runs Alembic migrations
(`AUTO_RUN_MIGRATIONS`, on by default), and — if the database is empty and
`ADMIN_EMAIL`/`ADMIN_PASSWORD` are set — creates the initial admin user.
Health check: `GET /api/ping`. Uploaded logos are kept in the `bracket_uploads`
volume.

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
  deletes the event and decides who helps. Nobody needs to share a login.
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

- **Client addresses.** Login and registration are rate limited per client IP.
  The backend only trusts `X-Forwarded-For` from the addresses in
  `FORWARDED_ALLOW_IPS`; otherwise every request seems to come from the proxy,
  and all visitors share one limit. Docker forwards the published port from the
  network's gateway, so set it to that address (the network is named
  `<compose project>_bracket_lan`):

  ```bash
  docker network inspect bracket_bracket_lan -f '{{(index .IPAM.Config 0).Gateway}}'
  ```

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

Tests need a PostgreSQL database; stamp it first so that the app doesn't replay
the migrations on top of the tables the tests create:

```bash
cd backend
ENVIRONMENT=DEVELOPMENT JWT_SECRET=... PG_DSN=... uv run alembic stamp head
ENVIRONMENT=DEVELOPMENT JWT_SECRET=... PG_DSN=... uv run pytest
```

Frontend:

```bash
cd frontend
corepack enable
pnpm install
pnpm dev
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

### Public pages

`GET /api/tournaments/{id}/details` returns everything the Details pages show in
one response, which the backend keeps for a few seconds. A venue full of phones
that refresh every half minute costs one database read per tournament, not one
per visitor.
