from fastapi import APIRouter

from bracket.config import config
from bracket.routes.models import AuthFeatureFlags, AuthFeatureFlagsResponse

router = APIRouter(prefix=config.api_prefix)


@router.get("/ping", summary="Healthcheck ping")
async def ping() -> str:
    return "ping"


@router.get("/auth/features", response_model=AuthFeatureFlagsResponse)
async def get_auth_features() -> AuthFeatureFlagsResponse:
    return AuthFeatureFlagsResponse(
        data=AuthFeatureFlags(
            user_registration_enabled=config.allow_user_registration,
        )
    )
