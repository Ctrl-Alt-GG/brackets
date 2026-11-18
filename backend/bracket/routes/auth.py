from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Response, status
from fastapi.security import OAuth2PasswordRequestForm
from starlette.requests import Request

from bracket.config import config
from bracket.database import DbSession
from bracket.logic.authentication import (
    authenticate_user,
    end_session,
    is_frontend_request,
    issue_token,
)
from bracket.models.db.user import Token
from bracket.routes.access import CredentialsDependency, reject_cross_site_request
from bracket.utils.errors import unauthorized
from bracket.utils.rate_limit import (
    enforce_account_lockout,
    get_account_lockout_key,
    rate_limit,
    record_account_failure,
    reset_account_failures,
)
from bracket.utils.security import normalize_email

router = APIRouter(prefix=config.api_prefix)


@router.post(
    "/token",
    response_model=Token,
    dependencies=[Depends(reject_cross_site_request), Depends(rate_limit("10/5minutes"))],
)
async def login_for_access_token(
    request: Request,
    response: Response,
    session: DbSession,
    form_data: Annotated[OAuth2PasswordRequestForm, Depends()],
) -> Token:
    try:
        normalized_email = normalize_email(form_data.username)
    except ValueError:
        normalized_email = form_data.username.strip().lower()

    # Failures are counted per account and client address together. Counting per account alone
    # would let anyone who knows an organizer's email keep them locked out.
    lockout_key = get_account_lockout_key(normalized_email, request)
    await enforce_account_lockout(lockout_key)

    user = await authenticate_user(session, form_data.username, form_data.password)
    if not user:
        retry_after = await record_account_failure(lockout_key)
        if retry_after is not None:
            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                detail="Incorrect email or password",
                headers={"Retry-After": str(retry_after)},
            )
        raise unauthorized("Incorrect email or password")

    await reset_account_failures(lockout_key)
    return issue_token(
        response,
        user.id,
        user.name,
        user.password_hash,
        include_token=not is_frontend_request(request),
    )


@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT)
async def logout(
    response: Response, session: DbSession, credentials: CredentialsDependency
) -> None:
    """
    Ends the session: its cookie is removed from this browser, and its tokens stop working, also
    for anyone who copied one.
    """
    await end_session(session, credentials, response)
