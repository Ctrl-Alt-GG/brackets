from fastapi import APIRouter, Depends, HTTPException, Response
from heliclockter import datetime_utc, timedelta
from starlette import status
from starlette.requests import Request

from bracket.config import config
from bracket.models.db.account import UserAccountType
from bracket.models.db.user import (
    UserInsertable,
    UserPasswordToUpdate,
    UserPublic,
    UserToRegister,
    UserToUpdate,
)
from bracket.routes.auth import (
    Token,
    create_access_token,
    user_authenticated,
)
from bracket.routes.models import SuccessResponse, TokenResponse, UserPublicResponse
from bracket.sql.users import (
    check_whether_email_is_in_use,
    create_user,
    get_user_by_id,
    update_user,
    update_user_password,
)
from bracket.utils.id_types import UserId
from bracket.utils.rate_limit import limiter
from bracket.utils.security import hash_password
from bracket.utils.types import assert_some

router = APIRouter(prefix=config.api_prefix)


@router.get("/users/me", response_model=UserPublicResponse)
async def get_user(user_public: UserPublic = Depends(user_authenticated)) -> UserPublicResponse:
    return UserPublicResponse(data=user_public)


@router.get("/users/{user_id}", response_model=UserPublicResponse)
async def get_me(
    user_id: UserId, user_public: UserPublic = Depends(user_authenticated)
) -> UserPublicResponse:
    if user_public.id != user_id:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Can't view details of this user")

    return UserPublicResponse(data=user_public)


@router.put("/users/{user_id}", response_model=UserPublicResponse)
async def update_user_details(
    user_id: UserId,
    user_to_update: UserToUpdate,
    user_public: UserPublic = Depends(user_authenticated),
) -> UserPublicResponse:
    if user_public.id != user_id:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Can't change details of this user")

    await update_user(user_public.id, user_to_update)
    user_updated = await get_user_by_id(user_id)
    return UserPublicResponse(data=assert_some(user_updated))


@router.put("/users/{user_id}/password", response_model=SuccessResponse)
async def put_user_password(
    user_id: UserId,
    user_to_update: UserPasswordToUpdate,
    user_public: UserPublic = Depends(user_authenticated),
) -> SuccessResponse:
    if user_public.id != user_id:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Can't change details of this user")
    await update_user_password(user_public.id, hash_password(user_to_update.password))
    return SuccessResponse()


@router.post("/users/register", response_model=TokenResponse)
@limiter.limit("5/15minutes")
async def register_user(
    request: Request, response: Response, user_to_register: UserToRegister
) -> TokenResponse:
    if not config.allow_user_registration:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Account creation is unavailable for now")

    del request, response

    user = UserInsertable(
        email=user_to_register.email,
        password_hash=hash_password(user_to_register.password),
        name=user_to_register.name,
        created=datetime_utc.now(),
        account_type=UserAccountType.REGULAR,
    )
    if await check_whether_email_is_in_use(user.email):
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Email address already in use")

    user_created = await create_user(user)
    access_token_expires = timedelta(minutes=config.access_token_expire_minutes)
    access_token = create_access_token(
        data={"sub": user_created.email, "user": user_created.email},
        expires_delta=access_token_expires,
    )
    return TokenResponse(
        data=Token(
            access_token=access_token,
            token_type="bearer",
            user_id=user_created.id,
            name=user_created.name,
        )
    )
