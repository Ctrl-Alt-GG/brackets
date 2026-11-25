"""The dependencies that decide who may make a request."""

import re
from typing import Annotated
from urllib.parse import urlsplit

from fastapi import Depends, HTTPException, Response, status
from fastapi.security import APIKeyCookie, OAuth2PasswordBearer
from sqlalchemy.ext.asyncio import AsyncSession
from starlette.requests import Request

from bracket import orm
from bracket.config import config
from bracket.database import READ_METHODS, DbSession, session_scope
from bracket.logic.authentication import (
    CSRF_HEADER,
    CSRF_HEADER_VALUE,
    SESSION_COOKIE,
    Credentials,
    get_session_user,
)
from bracket.logic.organizers import check_user_owns_tournament
from bracket.models.db.user import UserPublic
from bracket.models.enums import TournamentStatus
from bracket.sql.organizers import is_organizer
from bracket.sql.tournaments import lock_tournament
from bracket.utils.errors import forbidden, unauthorized
from bracket.utils.i18n import gettext
from bracket.utils.id_types import TournamentId
from bracket.utils.rate_limit import enforce_visitor_read_limit

# API clients send the token as a bearer token instead.
oauth2_scheme = OAuth2PasswordBearer(tokenUrl=f"{config.api_prefix}/token", auto_error=False)
session_cookie = APIKeyCookie(name=SESSION_COOKIE, auto_error=False)


async def get_credentials(
    bearer_token: str | None = Depends(oauth2_scheme),
    cookie_token: str | None = Depends(session_cookie),
) -> Credentials | None:
    if bearer_token:
        return Credentials(token=bearer_token, from_cookie=False)
    if cookie_token:
        return Credentials(token=cookie_token, from_cookie=True)
    return None


async def protect_session_from_csrf(request: Request) -> None:
    """
    Other sites can make a browser send its cookies, but not a custom header: browsers ask the
    API's CORS allowlist first. So a state-changing request that is signed in with the session
    cookie has to send one. This is OWASP's custom request header defense against CSRF.
    """
    if (
        request.method not in READ_METHODS
        and SESSION_COOKIE in request.cookies
        # A request with its own credentials doesn't use the ambient cookie.
        and "Authorization" not in request.headers
        and request.headers.get(CSRF_HEADER) != CSRF_HEADER_VALUE
    ):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=gettext(
                "Requests signed in with the session cookie need the {header} header",
                header=CSRF_HEADER,
            ),
        )


def _origin(url: str) -> str:
    parts = urlsplit(url)
    return f"{parts.scheme}://{parts.netloc}".lower()


def is_own_origin(origin: str, request: Request) -> bool:
    origin = origin.lower()
    return (
        origin in {_origin(config.base_url), _origin(str(request.base_url))}
        or origin in {allowed.lower().rstrip("/") for allowed in config.cors_origins}
        or bool(config.cors_origin_regex and re.fullmatch(config.cors_origin_regex, origin))
    )


async def reject_cross_site_request(request: Request) -> None:
    """
    Signing in sets the session cookie, and there is no session yet for
    `protect_session_from_csrf` to protect. Without this, another site could post its own
    credentials and sign a visitor in to an account it controls (login CSRF).

    Browsers say where a request comes from, and scripts can't change that. API clients send
    neither header and pass.
    """
    fetch_site = request.headers.get("Sec-Fetch-Site")
    origin = request.headers.get("Origin")
    if fetch_site == "cross-site" or (origin is not None and not is_own_origin(origin, request)):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=gettext("This request can't be made from another site"),
        )


CredentialsDependency = Annotated[Credentials | None, Depends(get_credentials)]


async def user_authenticated(
    session: DbSession, response: Response, credentials: CredentialsDependency
) -> UserPublic:
    user = await get_session_user(session, credentials, response)
    if user is None:
        raise unauthorized()
    return user


AuthenticatedUser = Annotated[UserPublic, Depends(user_authenticated)]


async def user_authenticated_for_tournament(
    tournament_id: TournamentId, session: DbSession, request: Request, user: AuthenticatedUser
) -> UserPublic:
    """
    An organizer of the tournament. A command locks the tournament before it checks access, and
    holds the lock until it ends, so that competitor checks and score writes can't interleave.

    Changing who runs a tournament is a command on it as well: someone who loses access loses it
    once the commands that were let in have finished, and a command that waits for the
    tournament sees its organizers as they are after the change.
    """
    is_command = request.method not in READ_METHODS
    # Also for a tournament that doesn't exist, so that the answer doesn't tell which ids do.
    if (is_command and not await lock_tournament(session, tournament_id)) or not await is_organizer(
        session, tournament_id, user.id
    ):
        raise forbidden(gettext("You don't have access to this tournament"))

    return user


async def user_owns_tournament(
    tournament_id: TournamentId,
    session: DbSession,
    user: Annotated[UserPublic, Depends(user_authenticated_for_tournament)],
) -> UserPublic:
    """
    The tournament's owner. Organizers who were added to help can't decide who helps, hand the
    tournament over or delete it.
    """
    await check_user_owns_tournament(session, tournament_id, user.id)
    return user


async def authenticate_tournament_or_public(
    session: AsyncSession,
    tournament_id: TournamentId,
    response: Response,
    credentials: Credentials | None,
) -> UserPublic | None:
    """
    The organizer of the tournament, or `None` for anyone else while the tournament is public.
    """
    user = await get_session_user(session, credentials, response)
    if user is not None and await is_organizer(session, tournament_id, user.id):
        return user

    tournament = await session.get(orm.Tournament, tournament_id)
    if tournament is not None and (
        tournament.dashboard_public or tournament.status is TournamentStatus.OPEN
    ):
        return None

    if user is not None:
        raise forbidden(gettext("You don't have access to this tournament"))
    raise unauthorized(gettext("Could not validate credentials or page is not publicly available"))


async def user_authenticated_or_public_dashboard(
    tournament_id: TournamentId,
    session: DbSession,
    response: Response,
    credentials: CredentialsDependency,
) -> UserPublic | None:
    return await authenticate_tournament_or_public(session, tournament_id, response, credentials)


async def user_authenticated_for_cached_dashboard(
    tournament_id: TournamentId, response: Response, credentials: CredentialsDependency
) -> UserPublic | None:
    # Cached loads own their session and may outlive the initiating request. Release the
    # authorization connection first so waiting visitors cannot exhaust the shared pool.
    async with session_scope(read_only=True) as session:
        return await authenticate_tournament_or_public(
            session, tournament_id, response, credentials
        )


async def user_authenticated_or_rate_limited_visitor(
    request: Request,
    user: Annotated[UserPublic | None, Depends(user_authenticated_or_public_dashboard)],
) -> UserPublic | None:
    """
    `user_authenticated_or_public_dashboard` for answers that take a lot of work, such as replaying
    every match. The Details pages never ask for them, so a visitor who does is rate limited. The
    tournament's organizers are not.
    """
    if user is None:
        await enforce_visitor_read_limit(request)
    return user


async def user_authenticated_or_visitor(
    session: DbSession, response: Response, credentials: CredentialsDependency
) -> UserPublic | None:
    """
    The signed-in user, or `None` for a visitor.

    Credentials that are no longer valid count as a visitor's. A browser keeps sending the cookie
    of a session that ended elsewhere (a password change, for example) until it expires, and
    pages that anyone may see must keep working for it meanwhile.
    """
    return await get_session_user(session, credentials, response)
