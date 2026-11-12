from __future__ import annotations

from math import ceil
from time import time

from fastapi import HTTPException
from limits import RateLimitItemPerMinute
from limits.storage import storage_from_string
from limits.strategies import FixedWindowRateLimiter
from slowapi import Limiter
from slowapi.util import get_remote_address
from starlette.requests import Request

from bracket.config import config

limiter = Limiter(
    key_func=get_remote_address,
    headers_enabled=True,
    default_limits=[],
    storage_uri=config.rate_limit_storage_uri,
)
account_lockout_storage = storage_from_string(config.rate_limit_storage_uri)
account_lockout_limiter = FixedWindowRateLimiter(account_lockout_storage)
ACCOUNT_LOCKOUT_LIMIT = RateLimitItemPerMinute(5, 15, namespace="account_lockout")


def get_account_lockout_key(email: str, request: Request | None = None, address: str = "") -> str:
    """
    Failed logins are counted per account and client address together.

    Counting per account alone lets anyone who knows an organizer's email lock them out by
    failing on purpose. This way an attacker only locks out their own address, and the request
    limit per address still bounds how fast one address can guess.
    """
    client = get_remote_address(request) if request is not None else address
    return f"{email}|{client}"


def get_account_lockout_retry_after(identifier: str) -> int | None:
    window_stats = account_lockout_limiter.get_window_stats(ACCOUNT_LOCKOUT_LIMIT, identifier)
    if window_stats.remaining > 0:
        return None

    return max(1, ceil(window_stats.reset_time - time()))


def enforce_account_lockout(identifier: str) -> None:
    """The same password-guessing budget applies to login and sensitive account changes."""
    if (retry_after := get_account_lockout_retry_after(identifier)) is not None:
        raise HTTPException(
            status_code=429,
            detail="Too many failed password attempts. Try again in a few minutes.",
            headers={"Retry-After": str(retry_after)},
        )


def record_account_failure(identifier: str) -> int | None:
    if account_lockout_limiter.hit(ACCOUNT_LOCKOUT_LIMIT, identifier):
        return None

    return get_account_lockout_retry_after(identifier)


def reset_account_failures(identifier: str) -> None:
    account_lockout_storage.clear(ACCOUNT_LOCKOUT_LIMIT.key_for(identifier))
