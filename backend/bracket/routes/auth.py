import hashlib
import hmac
import re
from dataclasses import dataclass
from http import HTTPMethod
from typing import Annotated, Any
from urllib.parse import urlsplit
from uuid import uuid4

import jwt
from fastapi import APIRouter, Depends, HTTPException, Response, status
from fastapi.security import APIKeyCookie, OAuth2PasswordBearer, OAuth2PasswordRequestForm
from heliclockter import datetime_utc, timedelta
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncConnection
from starlette.requests import Request

from bracket.config import Environment, config, environment
from bracket.database import DbConnection
from bracket.models.db.tournament import Tournament, TournamentStatus
from bracket.models.db.user import UserInDB, UserPublic
from bracket.schema import tournaments
from bracket.sql.tournaments import sql_get_tournament_by_endpoint_name
from bracket.sql.users import (
    get_user,
    get_user_access_to_club,
    get_user_access_to_tournament,
    get_user_in_db_with_session,
    revoke_session,
    update_user_password,
)
from bracket.utils.db import fetch_one_parsed
from bracket.utils.id_types import ClubId, TournamentId, UserId
from bracket.utils.rate_limit import (
    enforce_account_lockout,
    get_account_lockout_key,
    limiter,
    record_account_failure,
    reset_account_failures,
)
from bracket.utils.security import hash_password, normalize_email, verify_password
from bracket.utils.types import assert_some

router = APIRouter(prefix=config.api_prefix)

ALGORITHM = "HS256"

# The frontend's session is a cookie that scripts can't read, so an injected script can't steal it.
# In production it's secure, and the `__Host-` prefix makes browsers reject it unless it was set by
# this host itself, so another subdomain can't plant a session.
SECURE_SESSION_COOKIE = environment is Environment.PRODUCTION
SESSION_COOKIE = "__Host-bracket_session" if SECURE_SESSION_COOKIE else "bracket_session"
# The header that state-changing requests signed in with the session cookie have to send.
CSRF_HEADER = "X-Requested-With"
CSRF_HEADER_VALUE = "XMLHttpRequest"
SAFE_METHODS = frozenset({HTTPMethod.GET, HTTPMethod.HEAD, HTTPMethod.OPTIONS})

# API clients send the token as a bearer token instead.
oauth2_scheme = OAuth2PasswordBearer(tokenUrl=f"{config.api_prefix}/token", auto_error=False)
session_cookie = APIKeyCookie(name=SESSION_COOKIE, auto_error=False)

# Checked against when the email is unknown, so that a failed login takes as long whether or not
# the account exists, and the response time doesn't reveal which emails have an account.
DUMMY_PASSWORD_HASH = hash_password("password of an account that does not exist")


class Token(BaseModel):
    # Empty for the frontend, whose session is the cookie: see `issue_token`.
    access_token: str
    token_type: str
    user_id: UserId
    name: str


@dataclass(frozen=True)
class Credentials:
    token: str
    # The browser's session cookie, as opposed to the bearer token of an API client.
    from_cookie: bool


def unauthorized(detail: str = "Could not validate credentials") -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail=detail,
        headers={"WWW-Authenticate": "Bearer"},
    )


def forbidden(detail: str) -> HTTPException:
    """
    For a valid session that may not do this. The frontend signs out on 401, which would end a
    session that is fine.
    """
    return HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=detail)


async def protect_session_from_csrf(request: Request) -> None:
    """
    Other sites can make a browser send its cookies, but not a custom header: browsers ask the
    API's CORS allowlist first. So a state-changing request that is signed in with the session
    cookie has to send one. This is OWASP's custom request header defense against CSRF.
    """
    if (
        request.method not in SAFE_METHODS
        and SESSION_COOKIE in request.cookies
        # A request with its own credentials doesn't use the ambient cookie.
        and "Authorization" not in request.headers
        and request.headers.get(CSRF_HEADER) != CSRF_HEADER_VALUE
    ):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=f"Requests signed in with the session cookie need the {CSRF_HEADER} header",
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
            detail="This request can't be made from another site",
        )


def get_auth_hash(password_hash: str) -> str:
    """
    Changes with the user's password. Tokens carry it, so changing the password signs out every
    other session.
    """
    return hmac.new(config.jwt_secret.encode(), password_hash.encode(), hashlib.sha256).hexdigest()


async def authenticate_user(conn: AsyncConnection, email: str, password: str) -> UserInDB | None:
    try:
        normalized_email = normalize_email(email)
    except ValueError:
        return None

    user = await get_user(conn, normalized_email)
    if user is None:
        verify_password(password, DUMMY_PASSWORD_HASH)
        return None

    is_valid, updated_hash = verify_password(password, user.password_hash)
    if not is_valid:
        return None

    if updated_hash is not None:
        await update_user_password(conn, user.id, updated_hash)
        return user.model_copy(update={"password_hash": updated_hash})

    return user


def create_access_token(user_id: UserId, password_hash: str, session_id: str) -> str:
    # The subject is the user's id, not their email: it never changes, so a token stays valid when
    # its user changes their email, and can't be taken over by a later account with the same email.
    issued_at = datetime_utc.now()
    return jwt.encode(
        {
            "sub": str(user_id),
            "aud": config.jwt_audience,
            "exp": issued_at + timedelta(minutes=config.access_token_expire_minutes),
            "iat": issued_at,
            "iss": assert_some(config.jwt_issuer),
            "nbf": issued_at,
            "type": "access",
            "auth_hash": get_auth_hash(password_hash),
            # Stays the same while the session is renewed, so that logging out ends all of it.
            "sid": session_id,
        },
        config.jwt_secret,
        algorithm=ALGORITHM,
    )


def is_frontend_request(request: Request) -> bool:
    return request.headers.get(CSRF_HEADER) == CSRF_HEADER_VALUE


def issue_token(
    response: Response,
    user_id: UserId,
    name: str,
    password_hash: str,
    *,
    session_id: str | None = None,
    include_token: bool = True,
) -> Token:
    """
    Signs the user in: the session cookie, and the token in the body for API clients.

    The frontend only uses the cookie, which scripts can't read. `include_token=False` keeps the
    token out of the body for it, so that a script on the page can't read it there either.
    """
    access_token = create_access_token(user_id, password_hash, session_id or uuid4().hex)
    response.set_cookie(
        SESSION_COOKIE,
        access_token,
        max_age=config.access_token_expire_minutes * 60,
        secure=SECURE_SESSION_COOKIE,
        httponly=True,
        samesite="strict",
    )
    return Token(
        access_token=access_token if include_token else "",
        token_type="bearer",
        user_id=user_id,
        name=name,
    )


async def get_credentials(
    bearer_token: str | None = Depends(oauth2_scheme),
    cookie_token: str | None = Depends(session_cookie),
) -> Credentials | None:
    if bearer_token:
        return Credentials(token=bearer_token, from_cookie=False)
    if cookie_token:
        return Credentials(token=cookie_token, from_cookie=True)
    return None


def decode_token(token: str) -> dict[str, Any] | None:
    try:
        payload: dict[str, Any] = jwt.decode(
            token,
            config.jwt_secret,
            algorithms=[ALGORITHM],
            audience=config.jwt_audience,
            issuer=assert_some(config.jwt_issuer),
            options={
                "require": ["aud", "exp", "iat", "iss", "nbf", "sub", "type", "auth_hash", "sid"]
            },
        )
        int(payload["sub"])
    # `InvalidTokenError` is the base of every error a token can fail with, such as a bad signature,
    # expiry, or a wrong audience. Tokens from before the subject became the user id fail `int()`.
    except (jwt.InvalidTokenError, ValueError):
        return None

    return payload if payload["type"] == "access" else None


async def check_jwt_and_get_user(
    conn: AsyncConnection, credentials: Credentials | None, response: Response | None = None
) -> UserPublic | None:
    """
    The user the credentials belong to, or `None` when they aren't valid (any more).

    A session cookie that is past half its life is replaced through `response`, so an organizer
    who keeps working stays signed in, and one who walks away is signed out.
    """
    payload = decode_token(credentials.token) if credentials is not None else None
    if credentials is None or payload is None:
        return None

    session_id = str(payload["sid"])
    user = await get_user_in_db_with_session(conn, UserId(int(payload["sub"])), session_id)
    if user is None or not hmac.compare_digest(
        str(payload["auth_hash"]), get_auth_hash(user.password_hash)
    ):
        return None

    lifetime = config.access_token_expire_minutes * 60
    remaining = int(payload["exp"]) - datetime_utc.now().timestamp()
    if response is not None and credentials.from_cookie and remaining < lifetime / 2:
        issue_token(response, user.id, user.name, user.password_hash, session_id=session_id)

    return UserPublic.model_validate(user.model_dump(exclude={"password_hash"}))


async def user_authenticated(
    conn: DbConnection,
    response: Response,
    credentials: Credentials | None = Depends(get_credentials),
) -> UserPublic:
    user = await check_jwt_and_get_user(conn, credentials, response)
    if user is None:
        raise unauthorized()

    return user


async def user_authenticated_for_tournament(
    tournament_id: TournamentId,
    conn: DbConnection,
    response: Response,
    request: Request,
    credentials: Credentials | None = Depends(get_credentials),
) -> UserPublic:
    user = await check_jwt_and_get_user(conn, credentials, response)
    if user is None:
        raise unauthorized()
    # Also for a tournament that doesn't exist, so that the answer doesn't tell which ids do.
    if not await get_user_access_to_tournament(conn, tournament_id, user.id):
        raise forbidden("You don't have access to this tournament")

    if request.method not in SAFE_METHODS:
        # Competitor checks and score writes must share a lock: otherwise a score could be
        # recorded between checking that a slot is unused and assigning its replacement.
        locked = await conn.execute(
            tournaments.select().where(tournaments.c.id == tournament_id).with_for_update()
        )
        if locked.first() is None:
            raise forbidden("This tournament is no longer available")

    return user


async def user_authenticated_for_club(
    club_id: ClubId,
    conn: DbConnection,
    response: Response,
    credentials: Credentials | None = Depends(get_credentials),
) -> UserPublic:
    user = await check_jwt_and_get_user(conn, credentials, response)
    if user is None:
        raise unauthorized()
    if not await get_user_access_to_club(conn, club_id, user.id):
        raise forbidden("You don't have access to this event")

    return user


async def user_authenticated_or_public_dashboard(
    tournament_id: TournamentId,
    conn: DbConnection,
    response: Response,
    credentials: Credentials | None = Depends(get_credentials),
) -> UserPublic | None:
    """
    The organizer of the tournament, or `None` for anyone else while the tournament is public.
    """
    user = await check_jwt_and_get_user(conn, credentials, response)
    if user is not None and await get_user_access_to_tournament(conn, tournament_id, user.id):
        return user

    tournament = await fetch_one_parsed(
        conn, Tournament, tournaments.select().where(tournaments.c.id == tournament_id)
    )
    if tournament is not None and (
        tournament.dashboard_public or tournament.status is TournamentStatus.OPEN
    ):
        return None

    if user is not None:
        raise forbidden("You don't have access to this tournament")
    raise unauthorized("Could not validate credentials or page is not publicly available")


async def user_authenticated_or_public_dashboard_by_endpoint_name(
    conn: DbConnection,
    response: Response,
    credentials: Credentials | None = Depends(get_credentials),
    endpoint_name: str | None = None,
) -> UserPublic | None:
    if endpoint_name is not None:
        if await sql_get_tournament_by_endpoint_name(conn, endpoint_name) is None:
            raise unauthorized()
        return None

    if credentials is None:
        return None

    return await user_authenticated(conn, response, credentials)


@router.post("/token", response_model=Token, dependencies=[Depends(reject_cross_site_request)])
@limiter.limit("10/5minutes")
async def login_for_access_token(
    request: Request,
    response: Response,
    conn: DbConnection,
    form_data: Annotated[OAuth2PasswordRequestForm, Depends()],
) -> Token:
    try:
        normalized_email = normalize_email(form_data.username)
    except ValueError:
        normalized_email = form_data.username.strip().lower()

    # Failures are counted per account and client address together. Counting per account alone
    # would let anyone who knows an organizer's email keep them locked out.
    lockout_key = get_account_lockout_key(normalized_email, request)
    enforce_account_lockout(lockout_key)

    user = await authenticate_user(conn, form_data.username, form_data.password)
    if not user:
        retry_after = record_account_failure(lockout_key)
        if retry_after is not None:
            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                detail="Incorrect email or password",
                headers={"Retry-After": str(retry_after)},
            )
        raise unauthorized("Incorrect email or password")

    reset_account_failures(lockout_key)
    return issue_token(
        response,
        user.id,
        user.name,
        user.password_hash,
        include_token=not is_frontend_request(request),
    )


@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT)
async def logout(
    response: Response,
    conn: DbConnection,
    credentials: Credentials | None = Depends(get_credentials),
) -> None:
    """
    Ends the session: its cookie is removed from this browser, and its tokens stop working, also
    for anyone who copied one.
    """
    payload = decode_token(credentials.token) if credentials is not None else None
    if payload is not None:
        # A session's cookie is renewed while it is used, so a copy of it can hold a token that
        # lasts longer than the one presented here. No token issued until now outlives this.
        last_expiry = datetime_utc.now() + timedelta(minutes=config.access_token_expire_minutes)
        await revoke_session(conn, str(payload["sid"]), last_expiry)

    response.delete_cookie(
        SESSION_COOKIE, secure=SECURE_SESSION_COOKIE, httponly=True, samesite="strict"
    )
