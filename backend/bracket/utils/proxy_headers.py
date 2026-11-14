from starlette.datastructures import Headers
from starlette.types import ASGIApp, Receive, Scope, Send

from bracket.utils.logging import logger


class UntrustedProxyWarning:
    """
    Logs once when a request came through a proxy that `FORWARDED_ALLOW_IPS` doesn't list.

    uvicorn takes the client's address from `X-Forwarded-For` only when the request comes from a
    trusted proxy, and then the address is one of the header's entries. A request that has the
    header but none of its addresses came from a proxy whose header was ignored: every client
    then seems to have the proxy's address and shares its rate limits, so one client can lock all
    organizers out of logging in.
    """

    def __init__(self, app: ASGIApp) -> None:
        self.app = app
        self.warned = False

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] == "http" and not self.warned:
            forwarded_for = Headers(scope=scope).get("x-forwarded-for")
            client = scope.get("client")
            if (
                forwarded_for is not None
                and client is not None
                and client[0] not in {address.strip() for address in forwarded_for.split(",")}
            ):
                self.warned = True
                logger.warning(
                    "Ignoring X-Forwarded-For from %s, which FORWARDED_ALLOW_IPS doesn't list. "
                    "Every client behind that proxy shares one rate limit. See 'Reverse proxy' "
                    "in the README.",
                    client[0],
                )

        await self.app(scope, receive, send)
