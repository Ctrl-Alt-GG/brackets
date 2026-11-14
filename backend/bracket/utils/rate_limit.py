from __future__ import annotations

from math import ceil
from time import time

from fastapi import HTTPException
from limits import RateLimitItem, RateLimitItemPerMinute
from limits.storage import storage_from_string
from limits.strategies import FixedWindowRateLimiter
from slowapi import Limiter
from slowapi.util import get_remote_address
from starlette import status
from starlette.requests import Request

from bracket.config import config

limiter = Limiter(
    key_func=get_remote_address,
    headers_enabled=True,
    default_limits=[],
    storage_uri=config.rate_limit_storage_uri,
)
# The limits that routes check themselves, rather than through a `limiter` decorator.
rate_limit_storage = storage_from_string(config.rate_limit_storage_uri)
rate_limiter = FixedWindowRateLimiter(rate_limit_storage)
ACCOUNT_LOCKOUT_LIMIT = RateLimitItemPerMinute(5, 15, namespace="account_lockout")
# Every visitor's pages read the Details answer, which is cached. The other public reads replay a
# tournament's matches on every request, so a visitor who keeps asking for them could keep the
# server busy for everyone else.
VISITOR_READ_LIMIT = RateLimitItemPerMinute(60, namespace="visitor_reads")


def get_account_lockout_key(email: str, request: Request | None = None, address: str = "") -> str:
    """
    Failed logins are counted per account and client address together.

    Counting per account alone lets anyone who knows an organizer's email lock them out by
    failing on purpose. This way an attacker only locks out their own address, and the request
    limit per address still bounds how fast one address can guess.
    """
    client = get_remote_address(request) if request is not None else address
    return f"{email}|{client}"


def get_retry_after(limit: RateLimitItem, identifier: str) -> int | None:
    """Seconds until `identifier` may try again, or `None` while it is within the limit."""
    window_stats = rate_limiter.get_window_stats(limit, identifier)
    if window_stats.remaining > 0:
        return None

    return max(1, ceil(window_stats.reset_time - time()))


def get_account_lockout_retry_after(identifier: str) -> int | None:
    return get_retry_after(ACCOUNT_LOCKOUT_LIMIT, identifier)


def enforce_account_lockout(identifier: str) -> None:
    """The same password-guessing budget applies to login and sensitive account changes."""
    if (retry_after := get_account_lockout_retry_after(identifier)) is not None:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="Too many failed password attempts. Try again in a few minutes.",
            headers={"Retry-After": str(retry_after)},
        )


def record_account_failure(identifier: str) -> int | None:
    if rate_limiter.hit(ACCOUNT_LOCKOUT_LIMIT, identifier):
        return None

    return get_account_lockout_retry_after(identifier)


def reset_account_failures(identifier: str) -> None:
    rate_limit_storage.clear(ACCOUNT_LOCKOUT_LIMIT.key_for(identifier))


def enforce_visitor_read_limit(request: Request) -> None:
    address = get_remote_address(request)
    if not rate_limiter.hit(VISITOR_READ_LIMIT, address):
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="Too many requests. Try again in a minute.",
            headers={"Retry-After": str(get_retry_after(VISITOR_READ_LIMIT, address) or 60)},
        )
