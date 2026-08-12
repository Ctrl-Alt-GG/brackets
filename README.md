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
| `SECURITY_REVIEW.md` | Point-in-time review of the backend; not a live checklist |

## Deployment

The stack runs behind an external reverse proxy that terminates TLS for
`bracket.ctrl-alt-gg.hu`. Compose only binds to loopback:

- `127.0.0.1:3000` — frontend (nginx, container port 8080)
- `127.0.0.1:8400` — backend (container port 8400, API served under `/api`)

The proxy is expected to route `/` to the frontend and `/api/` to the backend.

Images come from GHCR and are built by the publish workflow whenever a `v*` tag
is pushed:

```
ghcr.io/ctrl-alt-gg/bracket-backend:<tag>
ghcr.io/ctrl-alt-gg/bracket-frontend:<tag>
```

`docker-compose.yml` pins explicit tags on purpose. Bump them when deploying a
new release rather than relying on `latest`.

Compose requires these values in the environment before `docker compose up`:

```bash
POSTGRES_DB=... POSTGRES_USER=... POSTGRES_PASSWORD=... JWT_SECRET=... \
  docker compose up -d
```

PostgreSQL 18 data is bind-mounted to `./postgres`. Redis has no volume: it only
holds rate-limit counters, which are disposable and reset when the container is
recreated.

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

### Why Redis

Redis is only used as shared storage for rate limiting: slowapi request limits
and the login lockout counter (5 failures per 15 minutes). In-memory storage
does not survive restarts and is not shared between Gunicorn workers, so the
backend refuses to start in `PRODUCTION` with `memory://`. Any storage backend
supported by `limits` works; the compose file uses the bundled Redis service.

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

### Checks

`backend/check.sh` is the quick backend formatting and typing check. Tests run
with `ENVIRONMENT=DEVELOPMENT`, a dedicated test database URL, and automatic
migrations disabled. The integration fixtures recreate the schema.

The frontend API client in `frontend/src/openapi` is generated. After changing
backend routes, regenerate it:

```bash
cd backend && uv run ./cli.py generate-openapi
cd ../frontend && pnpm openapi-ts
```

Frontend checks are `pnpm typecheck` and `pnpm format:check`.

## Releasing

Tag the commit and push the tag — the workflow does the rest:

```bash
git tag -a v0.1.2 -m "Release v0.1.2"
git push origin v0.1.2
```

Then update the image tags in `docker-compose.yml` and redeploy.

## License

AGPL-3.0, inherited from upstream. See [LICENSE](LICENSE).
