import hashlib
import hmac
from http import HTTPMethod
from typing import Annotated

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
    get_user_in_db,
    update_user_password,
)
from bracket.utils.db import fetch_one_parsed
from bracket.utils.id_types import ClubId, TournamentId, UserId
from bracket.utils.rate_limit import (
    get_account_lockout_retry_after,
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
    access_token: str
    token_type: str
    user_id: UserId
    name: str


def unauthorized(detail: str = "Could not validate credentials") -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail=detail,
        headers={"WWW-Authenticate": "Bearer"},
    )


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


def create_access_token(user_id: UserId, password_hash: str) -> str:
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
        },
        config.jwt_secret,
        algorithm=ALGORITHM,
    )


def issue_token(response: Response, user_id: UserId, name: str, password_hash: str) -> Token:
    """Signs the user in: the token is in the body for API clients, and the session cookie."""
    access_token = create_access_token(user_id, password_hash)
    response.set_cookie(
        SESSION_COOKIE,
        access_token,
        max_age=config.access_token_expire_minutes * 60,
        secure=SECURE_SESSION_COOKIE,
        httponly=True,
        samesite="strict",
    )
    return Token(access_token=access_token, token_type="bearer", user_id=user_id, name=name)


async def get_token(
    bearer_token: str | None = Depends(oauth2_scheme),
    cookie_token: str | None = Depends(session_cookie),
) -> str | None:
    return bearer_token or cookie_token


async def check_jwt_and_get_user(conn: AsyncConnection, token: str) -> UserPublic | None:
    try:
        payload = jwt.decode(
            token,
            config.jwt_secret,
            algorithms=[ALGORITHM],
            audience=config.jwt_audience,
            issuer=assert_some(config.jwt_issuer),
            options={"require": ["aud", "exp", "iat", "iss", "nbf", "sub", "type", "auth_hash"]},
        )
        user_id = UserId(int(payload["sub"]))
    # `InvalidTokenError` is the base of every error a token can fail with, such as a bad signature,
    # expiry, or a wrong audience. Tokens from before the subject became the user id fail `int()`.
    except (jwt.InvalidTokenError, ValueError):
        return None

    if payload["type"] != "access":
        return None

    user = await get_user_in_db(conn, user_id)
    if user is None or not hmac.compare_digest(
        str(payload["auth_hash"]), get_auth_hash(user.password_hash)
    ):
        return None

    return UserPublic.model_validate(user.model_dump(exclude={"password_hash"}))


async def user_authenticated(
    conn: DbConnection, token: str | None = Depends(get_token)
) -> UserPublic:
    user = await check_jwt_and_get_user(conn, token) if token is not None else None
    if user is None:
        raise unauthorized()

    return user


async def user_authenticated_for_tournament(
    tournament_id: TournamentId, conn: DbConnection, token: str | None = Depends(get_token)
) -> UserPublic:
    user = await check_jwt_and_get_user(conn, token) if token is not None else None
    if user is None or not await get_user_access_to_tournament(conn, tournament_id, user.id):
        raise unauthorized()

    return user


async def user_authenticated_for_club(
    club_id: ClubId, conn: DbConnection, token: str | None = Depends(get_token)
) -> UserPublic:
    user = await check_jwt_and_get_user(conn, token) if token is not None else None
    if user is None or not await get_user_access_to_club(conn, club_id, user.id):
        raise unauthorized()

    return user


async def user_authenticated_or_public_dashboard(
    tournament_id: TournamentId,
    conn: DbConnection,
    token: str | None = Depends(get_token),
) -> UserPublic | None:
    """
    The organizer of the tournament, or `None` for anyone else while the tournament is public.
    """
    if token is not None:
        user = await check_jwt_and_get_user(conn, token)
        if user is not None and await get_user_access_to_tournament(conn, tournament_id, user.id):
            return user

    tournament = await fetch_one_parsed(
        conn, Tournament, tournaments.select().where(tournaments.c.id == tournament_id)
    )
    if tournament is None or not (
        tournament.dashboard_public or tournament.status is TournamentStatus.OPEN
    ):
        raise unauthorized("Could not validate credentials or page is not publicly available")

    return None


async def user_authenticated_or_public_dashboard_by_endpoint_name(
    conn: DbConnection,
    token: str | None = Depends(get_token),
    endpoint_name: str | None = None,
) -> UserPublic | None:
    if endpoint_name is not None:
        if await sql_get_tournament_by_endpoint_name(conn, endpoint_name) is None:
            raise unauthorized()
        return None

    if token is None:
        return None

    return await user_authenticated(conn, token)


@router.post("/token", response_model=Token)
@limiter.limit("10/5minutes")
async def login_for_access_token(
    request: Request,
    response: Response,
    conn: DbConnection,
    form_data: Annotated[OAuth2PasswordRequestForm, Depends()],
) -> Token:
    del request

    try:
        normalized_email = normalize_email(form_data.username)
    except ValueError:
        normalized_email = form_data.username.strip().lower()

    retry_after = get_account_lockout_retry_after(normalized_email)
    if retry_after is not None:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="This account is temporarily locked after repeated failed login attempts",
            headers={"Retry-After": str(retry_after)},
        )

    user = await authenticate_user(conn, form_data.username, form_data.password)
    if not user:
        retry_after = record_account_failure(normalized_email)
        if retry_after is not None:
            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                detail="Incorrect email or password",
                headers={"Retry-After": str(retry_after)},
            )
        raise unauthorized("Incorrect email or password")

    reset_account_failures(normalized_email)
    return issue_token(response, user.id, user.name, user.password_hash)


@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT)
async def logout(response: Response) -> None:
    """Ends the session in this browser by removing its cookie."""
    response.delete_cookie(
        SESSION_COOKIE, secure=SECURE_SESSION_COOKIE, httponly=True, samesite="strict"
    )
