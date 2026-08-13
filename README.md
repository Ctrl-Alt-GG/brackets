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
| `.github/workflows/publish.yml` | Builds and pushes images to GHCR on `v*` tags |

## Deployment

Images come from GHCR and are built by the publish workflow whenever a `v*` tag
is pushed:

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
Health check: `GET /api/ping`.

## Configuration

Read from the environment by `backend/bracket/config.py`. `ENVIRONMENT` selects
the `PRODUCTION` or `DEVELOPMENT` config class, which picks up `prod.env` or
`dev.env` respectively.

| Variable | Notes |
| --- | --- |
| `ENVIRONMENT` | `PRODUCTION` / `DEVELOPMENT` |
| `JWT_SECRET` | Required. Startup fails below 32 characters |
| `PG_DSN` | PostgreSQL connection string |
| `BASE_URL` | Public URL; also the default JWT issuer |
| `API_PREFIX` | `/api` in our deployment; affects every route and the static mount |
| `CORS_ORIGINS` | Comma-separated allowlist. `*` is rejected |
| `RATE_LIMIT_STORAGE_URI` | Must not be `memory://` in production (see below) |
| `ALLOW_USER_REGISTRATION` | Self-service signup, enabled for our event |
| `ADMIN_EMAIL` / `ADMIN_PASSWORD` | Only used to bootstrap an empty database |
| `ACCESS_TOKEN_EXPIRE_MINUTES` | Minimum 5 |
| `UPLOAD_DIR` / `UPLOAD_MAX_BYTES` | Team and tournament logo uploads |

## Local development

Backend (needs [uv](https://docs.astral.sh/uv/) and a PostgreSQL instance):

```bash
cd backend
uv sync
uv run ./cli.py create-dev-db     # seeds a database with dummy data
uv run uvicorn bracket.app:app --reload --port 8400
```

`DevelopmentConfig` reads `backend/dev.env`, which is not committed. At minimum
it needs `JWT_SECRET` and `PG_DSN`.

Frontend:

```bash
cd frontend
corepack enable
pnpm install
pnpm dev
```

The SPA resolves its API base URL from `window.__BRACKET_RUNTIME_CONFIG__`
(injected by the container entrypoint from `API_BASE_URL`), then
`VITE_API_BASE_URL`, then `http://localhost:8400`. That indirection is what lets
one frontend image be deployed against any backend URL without a rebuild.
Set it to the backend **origin only** — the client appends `/api/...` itself, so
a trailing `/api` or `/` is stripped before use.
