from typing import Any

import jwt
from fastapi import APIRouter, Depends, HTTPException, Response, status
from fastapi.security import OAuth2PasswordBearer, OAuth2PasswordRequestForm
from heliclockter import datetime_utc, timedelta
from jwt import DecodeError, ExpiredSignatureError
from pydantic import BaseModel
from starlette.requests import Request

from bracket.config import config
from bracket.database import database
from bracket.models.db.tournament import Tournament, TournamentStatus
from bracket.models.db.user import UserInDB, UserPublic
from bracket.schema import tournaments
from bracket.sql.tournaments import sql_get_tournament_by_endpoint_name
from bracket.sql.users import get_user, get_user_access_to_club, get_user_access_to_tournament
from bracket.utils.db import fetch_all_parsed
from bracket.utils.id_types import ClubId, TournamentId, UserId
from bracket.utils.rate_limit import (
    get_account_lockout_retry_after,
    limiter,
    record_account_failure,
    reset_account_failures,
)
from bracket.utils.security import normalize_email, verify_password
from bracket.utils.types import assert_some

router = APIRouter(prefix=config.api_prefix)

ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = config.access_token_expire_minutes

oauth2_scheme = OAuth2PasswordBearer(tokenUrl=f"{config.api_prefix}/token")
oauth2_scheme_optional = OAuth2PasswordBearer(
    tokenUrl=f"{config.api_prefix}/token", auto_error=False
)


class Token(BaseModel):
    access_token: str
    token_type: str
    user_id: UserId
    name: str


class TokenData(BaseModel):
    email: str | None = None


async def authenticate_user(email: str, password: str) -> UserInDB | None:
    try:
        normalized_email = normalize_email(email)
    except ValueError:
        return None

    user = await get_user(normalized_email)

    if not user or not verify_password(password, user.password_hash):
        return None

    return user


def create_access_token(data: dict[str, Any], expires_delta: timedelta) -> str:
    to_encode = data.copy()
    if "sub" not in to_encode and "user" in to_encode:
        to_encode["sub"] = to_encode["user"]
    issued_at = datetime_utc.now()
    expire = issued_at + expires_delta
    to_encode.update(
        {
            "aud": config.jwt_audience,
            "exp": expire,
            "iat": issued_at,
            "iss": assert_some(config.jwt_issuer),
            "nbf": issued_at,
            "type": "access",
        }
    )
    return jwt.encode(to_encode, config.jwt_secret, algorithm=ALGORITHM)


async def check_jwt_and_get_user(token: str) -> UserPublic | None:
    try:
        payload = jwt.decode(
            token,
            config.jwt_secret,
            algorithms=[ALGORITHM],
            audience=config.jwt_audience,
            issuer=assert_some(config.jwt_issuer),
            options={"require": ["aud", "exp", "iat", "iss", "nbf", "sub", "type"]},
        )
        if payload.get("type") != "access":
            return None
        email = str(payload.get("sub"))
        token_data = TokenData(email=email)
    except (DecodeError, ExpiredSignatureError):
        return None

    user = await get_user(email=assert_some(token_data.email))
    if user is None:
        return None

    return UserPublic.model_validate(user.model_dump())


async def user_authenticated(token: str = Depends(oauth2_scheme)) -> UserPublic:
    user = await check_jwt_and_get_user(token)
    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Could not validate credentials",
            headers={"WWW-Authenticate": "Bearer"},
        )

    return UserPublic.model_validate(user.model_dump())


async def user_authenticated_for_tournament(
    tournament_id: TournamentId, token: str = Depends(oauth2_scheme)
) -> UserPublic:
    user = await check_jwt_and_get_user(token)

    if not user or not await get_user_access_to_tournament(tournament_id, user.id):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Could not validate credentials",
            headers={"WWW-Authenticate": "Bearer"},
        )

    return UserPublic.model_validate(user.model_dump())


async def user_authenticated_for_club(
    club_id: ClubId, token: str = Depends(oauth2_scheme)
) -> UserPublic:
    user = await check_jwt_and_get_user(token)

    if not user or not await get_user_access_to_club(club_id, user.id):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Could not validate credentials",
            headers={"WWW-Authenticate": "Bearer"},
        )

    return UserPublic.model_validate(user.model_dump())


async def user_authenticated_or_public_dashboard(
    tournament_id: TournamentId, request: Request
) -> UserPublic | None:
    try:
        token: str = assert_some(await oauth2_scheme(request))
        user = await check_jwt_and_get_user(token)
        if user is not None and await get_user_access_to_tournament(tournament_id, user.id):
            return user
    except HTTPException:
        pass

    tournaments_fetched = await fetch_all_parsed(
        database, Tournament, tournaments.select().where(tournaments.c.id == tournament_id)
    )
    if len(tournaments_fetched) < 1:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Could not validate credentials or page is not publicly available",
            headers={"WWW-Authenticate": "Bearer"},
        )

    tournament = tournaments_fetched[0]
    is_public_read = tournament.dashboard_public or tournament.status == TournamentStatus.OPEN
    if not is_public_read:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Could not validate credentials or page is not publicly available",
            headers={"WWW-Authenticate": "Bearer"},
        )

    return None


async def user_authenticated_or_public_dashboard_by_endpoint_name(
    token: str | None = Depends(oauth2_scheme_optional), endpoint_name: str | None = None
) -> UserPublic | None:
    if endpoint_name is not None:
        if await sql_get_tournament_by_endpoint_name(endpoint_name) is None:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Could not validate credentials",
                headers={"WWW-Authenticate": "Bearer"},
            )
        return None

    if token is None:
        return None

    return await user_authenticated(token)


@router.post("/token", response_model=Token)
@limiter.limit("10/5minutes")
async def login_for_access_token(
    request: Request,
    response: Response,
    form_data: OAuth2PasswordRequestForm = Depends(),
) -> Token:
    del request, response

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

    user = await authenticate_user(form_data.username, form_data.password)
    if not user:
        retry_after = record_account_failure(normalized_email)
        raise HTTPException(
            status_code=(
                status.HTTP_429_TOO_MANY_REQUESTS
                if retry_after is not None
                else status.HTTP_401_UNAUTHORIZED
            ),
            detail="Incorrect email or password",
            headers={
                "WWW-Authenticate": "Bearer",
                **({"Retry-After": str(retry_after)} if retry_after is not None else {}),
            },
        )

    reset_account_failures(normalized_email)

    access_token_expires = timedelta(minutes=config.access_token_expire_minutes)
    access_token = create_access_token(
        data={"sub": user.email, "user": user.email}, expires_delta=access_token_expires
    )
    return Token(access_token=access_token, token_type="bearer", user_id=user.id, name=user.name)
