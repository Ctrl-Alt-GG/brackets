"""Sessions: signing in, the tokens that carry a session, and checking them."""

import hashlib
import hmac
from dataclasses import dataclass
from functools import cache
from typing import Annotated, Literal
from uuid import uuid4

import jwt
from fastapi import Request, Response
from heliclockter import datetime_utc, timedelta
from pydantic import AwareDatetime, BaseModel, ConfigDict, Field, ValidationError
from sqlalchemy.ext.asyncio import AsyncSession

from bracket.config import Environment, config, environment
from bracket.models.db.user import Token, UserInDB, UserPublic
from bracket.sql.users import (
    get_user,
    get_user_in_db_with_session,
    revoke_session,
    update_user_password,
)
from bracket.utils.id_types import UserId
from bracket.utils.security import hash_password, normalize_email, verify_password_in_thread
from bracket.utils.types import assert_some

ALGORITHM = "HS256"

# The frontend's session is a cookie that scripts can't read, so an injected script can't steal it.
# In production it's secure, and the `__Host-` prefix makes browsers reject it unless it was set by
# this host itself, so another subdomain can't plant a session.
SECURE_SESSION_COOKIE = environment is Environment.PRODUCTION
SESSION_COOKIE = "__Host-bracket_session" if SECURE_SESSION_COOKIE else "bracket_session"
# The header that state-changing requests signed in with the session cookie have to send.
CSRF_HEADER = "X-Requested-With"
CSRF_HEADER_VALUE = "XMLHttpRequest"


@dataclass(frozen=True)
class Credentials:
    token: str
    # The browser's session cookie, as opposed to the bearer token of an API client.
    from_cookie: bool


class SessionClaims(BaseModel):
    """
    What a token says about its session. Only built from a token whose signature, issuer,
    audience and times PyJWT has verified.
    """

    model_config = ConfigDict(frozen=True)

    # The user's id, not their email: it never changes, so a token stays valid when its user
    # changes their email, and can't be taken over by a later account with the same email.
    user_id: Annotated[UserId, Field(alias="sub", gt=0)]
    # Stays the same while the session is renewed, so that logging out ends all of it.
    session_id: Annotated[str, Field(alias="sid", min_length=1, max_length=64)]
    # Changes with the password, so that changing it ends the account's other sessions.
    auth_hash: Annotated[str, Field(pattern=r"^[0-9a-f]{64}$")]
    expires: Annotated[AwareDatetime, Field(alias="exp")]
    type: Literal["access"]


@cache
def get_dummy_password_hash() -> str:
    """
    Checked against when the email is unknown, so that a failed login takes as long whether or
    not the account exists, and the response time doesn't reveal which emails have an account.
    """
    return hash_password("password of an account that does not exist")


def get_auth_hash(password_hash: str) -> str:
    """
    Changes with the user's password. Tokens carry it, so changing the password signs out every
    other session.
    """
    return hmac.new(config.jwt_secret.encode(), password_hash.encode(), hashlib.sha256).hexdigest()


async def authenticate_user(session: AsyncSession, email: str, password: str) -> UserInDB | None:
    try:
        normalized_email = normalize_email(email)
    except ValueError:
        return None

    user = await get_user(session, normalized_email)
    is_valid, updated_hash = await verify_password_in_thread(
        password, user.password_hash if user is not None else get_dummy_password_hash()
    )
    if user is None or not is_valid:
        return None

    if updated_hash is not None:
        await update_user_password(session, user.id, updated_hash)
        return user.model_copy(update={"password_hash": updated_hash})

    return user


def create_access_token(user_id: UserId, password_hash: str, session_id: str) -> str:
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
            "sid": session_id,
        },
        config.jwt_secret,
        algorithm=ALGORITHM,
    )


def decode_token(token: str) -> SessionClaims | None:
    """The claims of a valid token, or `None` for any token that isn't one."""
    try:
        return SessionClaims.model_validate(
            jwt.decode(
                token,
                config.jwt_secret,
                algorithms=[ALGORITHM],
                audience=config.jwt_audience,
                issuer=assert_some(config.jwt_issuer),
                options={
                    "require": [
                        "aud",
                        "exp",
                        "iat",
                        "iss",
                        "nbf",
                        "sub",
                        "type",
                        "auth_hash",
                        "sid",
                    ]
                },
            )
        )
    # `InvalidTokenError` is the base of every error a token can fail with, such as a bad signature,
    # expiry, or a wrong audience. Tokens from before the subject became the user id fail
    # validation, as do claims of the wrong shape.
    except (jwt.InvalidTokenError, ValidationError):
        return None


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


async def get_session_user(
    session: AsyncSession, credentials: Credentials | None, response: Response | None = None
) -> UserPublic | None:
    """
    The user the credentials belong to, or `None` when they aren't valid (any more).

    A session cookie that is past half its life is replaced through `response`, so an organizer
    who keeps working stays signed in, and one who walks away is signed out.
    """
    claims = decode_token(credentials.token) if credentials is not None else None
    if credentials is None or claims is None:
        return None

    user = await get_user_in_db_with_session(session, claims.user_id, claims.session_id)
    if user is None or not hmac.compare_digest(claims.auth_hash, get_auth_hash(user.password_hash)):
        return None

    lifetime = config.access_token_expire_minutes * 60
    remaining = (claims.expires - datetime_utc.now()).total_seconds()
    if response is not None and credentials.from_cookie and remaining < lifetime / 2:
        issue_token(response, user.id, user.name, user.password_hash, session_id=claims.session_id)

    return UserPublic.model_validate(user.model_dump(exclude={"password_hash"}))


async def end_session(
    session: AsyncSession, credentials: Credentials | None, response: Response
) -> None:
    """
    Remove the session's cookie from this browser, and make its tokens stop working, also for
    anyone who copied one.
    """
    claims = decode_token(credentials.token) if credentials is not None else None
    if claims is not None:
        # A session's cookie is renewed while it is used, so a copy of it can hold a token that
        # lasts longer than the one presented here. No token issued until now outlives this.
        last_expiry = datetime_utc.now() + timedelta(minutes=config.access_token_expire_minutes)
        await revoke_session(session, claims.session_id, last_expiry)

    response.delete_cookie(
        SESSION_COOKIE, secure=SECURE_SESSION_COOKIE, httponly=True, samesite="strict"
    )
