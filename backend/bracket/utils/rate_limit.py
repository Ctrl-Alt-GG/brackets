from __future__ import annotations

from math import ceil
from time import time

from limits import RateLimitItemPerMinute
from limits.storage import storage_from_string
from limits.strategies import FixedWindowRateLimiter
from slowapi import Limiter
from slowapi.util import get_remote_address

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


def get_account_lockout_retry_after(identifier: str) -> int | None:
    window_stats = account_lockout_limiter.get_window_stats(ACCOUNT_LOCKOUT_LIMIT, identifier)
    if window_stats.remaining > 0:
        return None

    return max(1, ceil(window_stats.reset_time - time()))


def record_account_failure(identifier: str) -> int | None:
    if account_lockout_limiter.hit(ACCOUNT_LOCKOUT_LIMIT, identifier):
        return None

    return get_account_lockout_retry_after(identifier)


def reset_account_failures(identifier: str) -> None:
    account_lockout_storage.clear(ACCOUNT_LOCKOUT_LIMIT.key_for(identifier))
