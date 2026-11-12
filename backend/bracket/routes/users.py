from fastapi import APIRouter, Depends, HTTPException, Response
from heliclockter import datetime_utc
from starlette import status
from starlette.requests import Request

from bracket.config import config
from bracket.database import DbConnection
from bracket.models.db.account import UserAccountType
from bracket.models.db.user import (
    UserInDB,
    UserInsertable,
    UserPasswordToUpdate,
    UserPublic,
    UserToRegister,
    UserToUpdate,
)
from bracket.routes.auth import (
    is_frontend_request,
    issue_token,
    reject_cross_site_request,
    user_authenticated,
)
from bracket.routes.models import SuccessResponse, TokenResponse, UserPublicResponse
from bracket.sql.users import (
    check_whether_email_is_in_use,
    create_user,
    get_user_by_id,
    get_user_in_db,
    update_user,
    update_user_password,
)
from bracket.utils.errors import UniqueIndex, check_unique_constraint_violation
from bracket.utils.id_types import UserId
from bracket.utils.rate_limit import (
    enforce_account_lockout,
    get_account_lockout_key,
    limiter,
    record_account_failure,
    reset_account_failures,
)
from bracket.utils.security import hash_password, validate_password_strength, verify_password
from bracket.utils.types import assert_some

router = APIRouter(prefix=config.api_prefix)

EMAIL_UNIQUE_INDEXES = {UniqueIndex.ix_users_email, UniqueIndex.ix_users_email_lower}


def check_is_same_user(user_public: UserPublic, user_id: UserId) -> None:
    if user_public.id != user_id:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "You can only manage your own account")


def current_password_is_valid(request: Request, user: UserInDB, password: str | None) -> bool:
    key = get_account_lockout_key(user.email, request)
    enforce_account_lockout(key)
    if password is None:
        return False
    if verify_password(password, user.password_hash)[0]:
        reset_account_failures(key)
        return True
    record_account_failure(key)
    return False


@router.get("/users/me", response_model=UserPublicResponse)
async def get_user(user_public: UserPublic = Depends(user_authenticated)) -> UserPublicResponse:
    return UserPublicResponse(data=user_public)


@router.get("/users/{user_id}", response_model=UserPublicResponse)
async def get_me(
    user_id: UserId, user_public: UserPublic = Depends(user_authenticated)
) -> UserPublicResponse:
    check_is_same_user(user_public, user_id)
    return UserPublicResponse(data=user_public)


@router.put("/users/{user_id}", response_model=UserPublicResponse)
async def update_user_details(
    conn: DbConnection,
    request: Request,
    user_id: UserId,
    user_to_update: UserToUpdate,
    user_public: UserPublic = Depends(user_authenticated),
) -> UserPublicResponse:
    check_is_same_user(user_public, user_id)

    # Whoever holds a session can use it, so changing the address the account signs in with
    # takes the password as well.
    if user_to_update.email != user_public.email:
        user = assert_some(await get_user_in_db(conn, user_public.id))
        if not current_password_is_valid(request, user, user_to_update.current_password):
            raise HTTPException(
                status.HTTP_400_BAD_REQUEST, "Enter your current password to change your email"
            )

    with check_unique_constraint_violation(EMAIL_UNIQUE_INDEXES):
        await update_user(conn, user_public.id, user_to_update)

    user_updated = await get_user_by_id(conn, user_id)
    return UserPublicResponse(data=assert_some(user_updated))


@router.put("/users/{user_id}/password", response_model=SuccessResponse)
@limiter.limit("10/5minutes")
async def put_user_password(
    request: Request,
    response: Response,
    conn: DbConnection,
    user_id: UserId,
    user_to_update: UserPasswordToUpdate,
    user_public: UserPublic = Depends(user_authenticated),
) -> SuccessResponse:
    """
    Asks for the current password as well, so that a stolen session can't lock the owner out.

    Signs out every other session. This one gets a new session cookie.
    """
    check_is_same_user(user_public, user_id)

    user = assert_some(await get_user_in_db(conn, user_public.id))
    if not current_password_is_valid(request, user, user_to_update.current_password):
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "The current password is incorrect")

    try:
        validate_password_strength(user_to_update.password, (user.email, user.name))
    except ValueError as exc:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, str(exc)) from exc

    password_hash = hash_password(user_to_update.password)
    await update_user_password(conn, user.id, password_hash)
    issue_token(response, user.id, user.name, password_hash)
    return SuccessResponse()


@router.post(
    "/users/register",
    response_model=TokenResponse,
    dependencies=[Depends(reject_cross_site_request)],
)
@limiter.limit("5/15minutes")
async def register_user(
    conn: DbConnection, request: Request, response: Response, user_to_register: UserToRegister
) -> TokenResponse:
    if not config.allow_user_registration:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Account creation is unavailable for now")

    user = UserInsertable(
        email=user_to_register.email,
        password_hash=hash_password(user_to_register.password),
        name=user_to_register.name,
        created=datetime_utc.now(),
        account_type=UserAccountType.REGULAR,
    )
    if await check_whether_email_is_in_use(conn, user.email):
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Email address already in use")

    with check_unique_constraint_violation(EMAIL_UNIQUE_INDEXES):
        user_created = await create_user(conn, user)

    return TokenResponse(
        data=issue_token(
            response,
            user_created.id,
            user_created.name,
            assert_some(user_created.password_hash),
            include_token=not is_frontend_request(request),
        )
    )
