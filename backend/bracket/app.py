from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from secure import (
    ContentSecurityPolicy,
    PermissionsPolicy,
    ReferrerPolicy,
    Secure,
    StrictTransportSecurity,
    XContentTypeOptions,
    XFrameOptions,
)
from secure.middleware import SecureASGIMiddleware
from slowapi.errors import RateLimitExceeded
from slowapi.extension import _rate_limit_exceeded_handler
from starlette.exceptions import HTTPException
from starlette.middleware.cors import CORSMiddleware
from starlette.responses import JSONResponse, Response
from starlette.staticfiles import StaticFiles

from bracket.config import Environment, config, environment
from bracket.database import engine
from bracket.routes import (
    auth,
    clubs,
    internals,
    matches,
    players,
    rankings,
    rounds,
    stage_item_inputs,
    stage_items,
    stages,
    teams,
    tournaments,
    users,
)
from bracket.utils.alembic import alembic_run_migrations
from bracket.utils.db_init import init_db_when_empty
from bracket.utils.logging import logger
from bracket.utils.rate_limit import limiter


@asynccontextmanager
async def lifespan(_: FastAPI) -> AsyncGenerator[None]:
    async with engine.begin() as conn:
        await init_db_when_empty(conn)

        if config.auto_run_migrations:
            await conn.run_sync(alembic_run_migrations)

    if environment is Environment.PRODUCTION and not config.is_cors_enabled():
        logger.warning("It's advised to set the `CORS_ORIGINS` environment variable in production")

    yield

    await engine.dispose()


routers = {
    "Auth": auth.router,
    "Clubs": clubs.router,
    "Internals": internals.router,
    "Matches": matches.router,
    "Players": players.router,
    "Rankings": rankings.router,
    "Rounds": rounds.router,
    "Stage Items": stage_items.router,
    "Stage Item Inputs": stage_item_inputs.router,
    "Stages": stages.router,
    "Teams": teams.router,
    "Tournaments": tournaments.router,
    "Users": users.router,
}

table_of_contents = "\n\n".join(
    [f"- [{tag}](#tag/{tag.replace(' ', '-')})" for tag in routers.keys()]
)


description = f"""
### Description
This API allows you to do everything the frontend of [Bracket](https://github.com/evroon/bracket)
allows you to do (the frontend uses this API as well).

Fore more information, see the [documentation](https://docs.bracketapp.nl).

### Table of Contents
*(links only work for [ReDoc](https://api.bracketapp.nl/redoc), not for Swagger UI)*

{table_of_contents}

### Links
GitHub: <https://github.com/evroon/bracket>

Docs: <https://docs.bracketapp.nl>

API docs (Redoc): <https://api.bracketapp.nl/redoc>

API docs (Swagger UI): <https://api.bracketapp.nl/docs>
"""

app = FastAPI(
    title="Bracket API",
    docs_url="/docs",
    version="1.0.0",
    lifespan=lifespan,
    summary="API for Bracket, an open source tournament system.",
    description=description,
    license_info={
        "name": "AGPL-3.0",
        "url": "https://www.gnu.org/licenses/agpl-3.0.en.html",
    },
)


async def handle_rate_limit_exceeded(request: Request, exc: Exception) -> Response:
    assert isinstance(exc, RateLimitExceeded)
    return _rate_limit_exceeded_handler(request, exc)


app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, handle_rate_limit_exceeded)

app.add_middleware(
    CORSMiddleware,
    allow_origins=config.cors_origins,
    allow_origin_regex=config.cors_origin_regex or None,
    allow_credentials=config.cors_allow_credentials,
    allow_methods=["*"],
    allow_headers=["*"],
)


app.add_middleware(
    SecureASGIMiddleware,
    secure=Secure(
        csp=ContentSecurityPolicy()
        .default_src("'self'")
        .base_uri("'self'")
        .frame_ancestors("'none'")
        .form_action("'self'")
        .img_src("'self'", "data:", "https:")
        .style_src("'self'", "'unsafe-inline'")
        .script_src("'self'", "'unsafe-inline'"),
        hsts=(
            StrictTransportSecurity().max_age(31536000).include_subdomains()
            if environment is Environment.PRODUCTION
            else None
        ),
        permissions=PermissionsPolicy().camera().geolocation().microphone(),
        referrer=ReferrerPolicy().no_referrer(),
        xcto=XContentTypeOptions().nosniff(),
        xfo=XFrameOptions().deny(),
    ),
)


@app.exception_handler(HTTPException)
async def validation_exception_handler(request: Request, exc: HTTPException) -> JSONResponse:
    return JSONResponse({"detail": exc.detail}, status_code=exc.status_code)


@app.exception_handler(Exception)
async def generic_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    logger.exception(
        "Unhandled request error for %s %s", request.method, request.url.path, exc_info=exc
    )
    return JSONResponse({"detail": "Internal server error"}, status_code=500)


app.mount(f"{config.api_prefix}/static", StaticFiles(directory="static"), name="static")

for tag, router in routers.items():
    assert router.prefix == config.api_prefix, f"Prefix not set on router with tag `{tag}`"
    app.include_router(router, tags=[tag])
