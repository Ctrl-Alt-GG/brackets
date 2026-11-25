"""
Rate limits, counted in the storage `RATE_LIMIT_STORAGE_URI` names (Redis in production) through
its asynchronous client, so a slow storage doesn't stop the event loop.
"""

from collections.abc import Awaitable, Callable
from math import ceil
from time import time

from fastapi import HTTPException
from limits import RateLimitItem, RateLimitItemPerMinute, parse
from limits.aio.storage import Storage
from limits.aio.strategies import FixedWindowRateLimiter
from limits.storage import storage_from_string
from starlette import status
from starlette.requests import Request
from starlette.responses import Response

from bracket.config import config
from bracket.utils.i18n import gettext


def _async_storage_uri(uri: str) -> str:
    """The configured URI names the storage; its asynchronous client has the `async+` scheme."""
    return uri if uri.startswith("async+") else f"async+{uri}"


def _create_storage() -> Storage:
    # The asyncio client of the `redis` package, which is installed anyway, for a Redis storage.
    storage = storage_from_string(
        _async_storage_uri(config.rate_limit_storage_uri), implementation="redispy"
    )
    assert isinstance(storage, Storage)
    return storage


rate_limit_storage = _create_storage()
rate_limiter = FixedWindowRateLimiter(rate_limit_storage)
ACCOUNT_LOCKOUT_LIMIT = RateLimitItemPerMinute(5, 15, namespace="account_lockout")
# Every visitor's pages read the Details answer, which is cached. The other public reads replay a
# tournament's matches on every request, so a visitor who keeps asking for them could keep the
# server busy for everyone else.
VISITOR_READ_LIMIT = RateLimitItemPerMinute(60, namespace="visitor_reads")


def get_remote_address(request: Request) -> str:
    """The client's address. Behind a trusted proxy, uvicorn takes it from `X-Forwarded-For`."""
    return request.client.host if request.client is not None else "127.0.0.1"


def get_account_lockout_key(email: str, request: Request | None = None, address: str = "") -> str:
    """
    Failed logins are counted per account and client address together.

    Counting per account alone lets anyone who knows an organizer's email lock them out by
    failing on purpose. This way an attacker only locks out their own address, and the request
    limit per address still bounds how fast one address can guess.
    """
    client = get_remote_address(request) if request is not None else address
    return f"{email}|{client}"


async def get_retry_after(limit: RateLimitItem, identifier: str) -> int | None:
    """Seconds until `identifier` may try again, or `None` while it is within the limit."""
    window_stats = await rate_limiter.get_window_stats(limit, identifier)
    if window_stats.remaining > 0:
        return None

    return max(1, ceil(window_stats.reset_time - time()))


def too_many_requests(detail: str, retry_after: int) -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_429_TOO_MANY_REQUESTS,
        detail=detail,
        headers={"Retry-After": str(retry_after)},
    )


async def enforce_account_lockout(identifier: str) -> None:
    """The same password-guessing budget applies to login and sensitive account changes."""
    if (retry_after := await get_retry_after(ACCOUNT_LOCKOUT_LIMIT, identifier)) is not None:
        raise too_many_requests(
            gettext("Too many failed password attempts. Try again in a few minutes."),
            retry_after,
        )


async def record_account_failure(identifier: str) -> int | None:
    if await rate_limiter.hit(ACCOUNT_LOCKOUT_LIMIT, identifier):
        return None

    return await get_retry_after(ACCOUNT_LOCKOUT_LIMIT, identifier)


async def reset_account_failures(identifier: str) -> None:
    await rate_limit_storage.clear(ACCOUNT_LOCKOUT_LIMIT.key_for(identifier))


async def enforce_visitor_read_limit(request: Request) -> None:
    address = get_remote_address(request)
    if not await rate_limiter.hit(VISITOR_READ_LIMIT, address):
        raise too_many_requests(
            gettext("Too many requests. Try again in a minute."),
            await get_retry_after(VISITOR_READ_LIMIT, address) or 60,
        )


def rate_limit(limit: str) -> Callable[[Request, Response], Awaitable[None]]:
    """
    A dependency that limits how often one client address can call a route, such as
    `"10/5minutes"`. Answers say how many calls are left.
    """
    item = parse(limit)

    async def dependency(request: Request, response: Response) -> None:
        identifier = f"{request.scope['route'].path}|{get_remote_address(request)}"
        allowed = await rate_limiter.hit(item, identifier)
        stats = await rate_limiter.get_window_stats(item, identifier)
        reset_after = max(1, ceil(stats.reset_time - time()))
        if not allowed:
            raise too_many_requests(
                gettext("Too many requests. Try again in a few minutes."), reset_after
            )
        response.headers["X-RateLimit-Limit"] = str(item.amount)
        response.headers["X-RateLimit-Remaining"] = str(stats.remaining)
        response.headers["X-RateLimit-Reset"] = str(ceil(stats.reset_time))

    return dependency
