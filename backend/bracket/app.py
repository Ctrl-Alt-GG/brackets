from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager

from fastapi import Depends, FastAPI, Request
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
from starlette.middleware.cors import CORSMiddleware
from starlette.responses import JSONResponse, Response

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

is_development = environment is Environment.DEVELOPMENT

app = FastAPI(
    title="Bracket API",
    version="1.0.0",
    lifespan=lifespan,
    summary="API of the Ctrl-Alt-GG fork of Bracket, an open source tournament system.",
    description="Everything the Bracket frontend does, it does through this API.",
    license_info={
        "name": "AGPL-3.0",
        "url": "https://www.gnu.org/licenses/agpl-3.0.en.html",
    },
    # The interactive docs load Swagger UI and ReDoc from a CDN, which the production security
    # headers don't allow, so only development serves them.
    openapi_url="/openapi.json" if is_development else None,
    dependencies=[Depends(auth.protect_session_from_csrf)],
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
        # The API only answers with JSON and uploaded images, so nothing may load or frame it.
        # Development leaves it out, so that the interactive docs work.
        csp=(
            None
            if is_development
            else ContentSecurityPolicy().default_src("'none'").frame_ancestors("'none'")
        ),
        hsts=(
            None
            if is_development
            else StrictTransportSecurity().max_age(31536000).include_subdomains()
        ),
        permissions=PermissionsPolicy().camera().geolocation().microphone(),
        referrer=ReferrerPolicy().no_referrer(),
        xcto=XContentTypeOptions().nosniff(),
        xfo=XFrameOptions().deny(),
    ),
)


@app.exception_handler(Exception)
async def generic_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    logger.exception(
        "Unhandled request error for %s %s", request.method, request.url.path, exc_info=exc
    )
    return JSONResponse({"detail": "Internal server error"}, status_code=500)


for tag, router in routers.items():
    assert router.prefix == config.api_prefix, f"Prefix not set on router with tag `{tag}`"
    app.include_router(router, tags=[tag])
