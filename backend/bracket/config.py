import logging
import os
from enum import auto
from typing import Annotated, Any

from pydantic import Field, PostgresDsn, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

from bracket.utils.security import validate_password_strength
from bracket.utils.types import EnumAutoStr


class Environment(EnumAutoStr):
    PRODUCTION = auto()
    DEVELOPMENT = auto()

    def get_log_level(self) -> int:
        return {
            Environment.DEVELOPMENT: logging.DEBUG,
            Environment.PRODUCTION: logging.INFO,
        }[self]


class Config(BaseSettings):
    # `enable_decoding=False` keeps pydantic-settings from JSON-decoding complex fields such as
    # `cors_origins`, so the `mode="before"` validator below receives the raw comma-separated
    # string that operators actually put in the env file.
    model_config = SettingsConfigDict(enable_decoding=False)

    admin_email: str | None = None
    admin_password: str | None = None
    allow_insecure_http_sso: bool = False
    allow_user_registration: bool = True
    base_url: str = "http://localhost:8400"
    cors_origin_regex: str = ""
    cors_origins: list[str] = Field(default_factory=list)
    cors_allow_credentials: bool = False
    jwt_secret: str
    jwt_audience: str = "bracket-api"
    jwt_issuer: str | None = None
    access_token_expire_minutes: int = 30
    auto_run_migrations: bool = True
    pg_dsn: PostgresDsn = PostgresDsn("postgresql://user:pass@localhost:5432/db")
    api_prefix: str = ""
    rate_limit_storage_uri: str = "memory://"
    upload_dir: str = "uploads"
    upload_max_bytes: int = 2 * 1024 * 1024

    def is_cors_enabled(self) -> bool:
        return bool(self.cors_origins or self.cors_origin_regex)

    @field_validator("cors_origins", mode="before")
    @classmethod
    def validate_cors_origins(cls, value: Any) -> list[str]:
        if value is None:
            return []

        if isinstance(value, str):
            stripped = value.strip()
            if not stripped:
                return []
            if stripped == "*":
                raise ValueError("CORS_ORIGINS must be an explicit allowlist, not `*`")
            return [origin.strip() for origin in stripped.split(",") if origin.strip()]

        if isinstance(value, list):
            origins = [str(origin).strip() for origin in value if str(origin).strip()]
            if any(origin == "*" for origin in origins):
                raise ValueError("CORS_ORIGINS must be an explicit allowlist, not `*`")
            return origins

        raise TypeError("CORS_ORIGINS must be a comma-separated string or list of origins")

    @model_validator(mode="after")
    def validate_security_settings(self) -> "Config":
        if len(self.jwt_secret) < 32:
            raise ValueError("JWT_SECRET must be at least 32 characters long")

        if self.admin_password is not None:
            validate_password_strength(self.admin_password)

        if self.cors_allow_credentials and not self.is_cors_enabled():
            raise ValueError("Credentialed CORS requires an explicit origin allowlist or regex")

        if self.jwt_issuer is None:
            self.jwt_issuer = self.base_url.rstrip("/")

        if self.access_token_expire_minutes < 5:
            raise ValueError("ACCESS_TOKEN_EXPIRE_MINUTES must be at least 5 minutes")

        if self.upload_max_bytes <= 0:
            raise ValueError("UPLOAD_MAX_BYTES must be greater than zero")

        return self


class DevelopmentConfig(Config):
    admin_email: Annotated[str | None, Field("test@example.org")]
    allow_insecure_http_sso: Annotated[bool, Field(True)]
    cors_origin_regex: Annotated[str, Field(r"^https?://(localhost|127\.0\.0\.1)(:\d+)?$")]

    model_config = SettingsConfigDict(env_file="dev.env")


class ProductionConfig(Config):
    model_config = SettingsConfigDict(env_file="prod.env")


environment = Environment(
    os.getenv("ENVIRONMENT", "DEVELOPMENT").upper()
)
config: Config

match environment:
    case Environment.DEVELOPMENT:
        config = DevelopmentConfig()  # type: ignore[call-arg]
    case Environment.PRODUCTION:
        config = ProductionConfig()  # type: ignore[call-arg]

if environment is Environment.PRODUCTION and config.rate_limit_storage_uri == "memory://":
    raise RuntimeError(
        "RATE_LIMIT_STORAGE_URI must use a shared backend in production; "
        "memory:// is not sufficient"
    )
