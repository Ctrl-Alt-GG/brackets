from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from http import HTTPMethod

import aiohttp
import pytest
from heliclockter import datetime_utc
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncConnection

from bracket.database import engine
from bracket.models.db.account import UserAccountType
from bracket.models.db.user import User, UserInsertable
from bracket.routes.auth import SESSION_COOKIE
from bracket.schema import users
from bracket.sql.users import create_user, delete_user, get_user_by_id
from bracket.utils.db import fetch_one_parsed_certain
from bracket.utils.security import hash_password, verify_password
from bracket.utils.types import assert_some
from tests.integration_tests.api.shared import (
    get_root_uvicorn_url,
    send_auth_request,
    send_request,
)
from tests.integration_tests.mocks import get_mock_token
from tests.integration_tests.models import AuthContext


@pytest.mark.asyncio(loop_scope="session")
async def test_users_endpoint(
    startup_and_shutdown_uvicorn_server: None, auth_context: AuthContext
) -> None:
    expected_data = {
        "data": {
            "email": auth_context.user.email,
            "created": "2000-01-01T00:00:00Z",
            "id": auth_context.user.id,
            "name": "Donald Duck",
            "account_type": UserAccountType.REGULAR.value,
        },
    }

    assert (
        await send_auth_request(HTTPMethod.GET, f"users/{auth_context.user.id}", auth_context, {})
        == expected_data
    )

    assert await send_auth_request(HTTPMethod.GET, "users/me", auth_context, {}) == expected_data


@pytest.mark.asyncio(loop_scope="session")
async def test_create_user(
    conn: AsyncConnection, startup_and_shutdown_uvicorn_server: None, auth_context: AuthContext
) -> None:
    body = {
        "name": "Some new name",
        "email": "some_email@email.com",
        "password": "my test pass",
    }
    response = await send_request(HTTPMethod.POST, "users/register", None, body)
    assert "data" in response, response
    assert response["data"]["token_type"] == "bearer"
    assert response["data"]["user_id"]
    await delete_user(conn, response["data"]["user_id"])


@asynccontextmanager
async def temporary_user() -> AsyncIterator[tuple[User, dict[str, str]]]:
    user_created = None
    try:
        new_user = UserInsertable(
            email="email123@example.org",
            password_hash=hash_password("some password"),
            name="name",
            created=datetime_utc.now(),
            account_type=UserAccountType.REGULAR,
        )
        async with engine.begin() as conn:
            user_created = await create_user(conn, new_user)
        headers = {"Authorization": f"Bearer {get_mock_token(user_created)}"}
        yield user_created, headers
    finally:
        if user_created is not None:
            async with engine.begin() as conn:
                await delete_user(conn, user_created.id)


@pytest.mark.asyncio(loop_scope="session")
async def test_update_user(
    conn: AsyncConnection, startup_and_shutdown_uvicorn_server: None, auth_context: AuthContext
) -> None:
    async with temporary_user() as (user_created, headers):
        body = {"name": "Some new name", "email": "some_email@email.com"}
        response = await send_auth_request(
            HTTPMethod.PUT,
            f"users/{user_created.id}",
            auth_context.model_copy(update={"user": user_created, "headers": headers}),
            json=body,
        )
        updated_user = assert_some(await get_user_by_id(conn, user_created.id))
        assert response["data"]["name"] == body["name"]
        assert updated_user.name == body["name"]


@pytest.mark.asyncio(loop_scope="session")
async def test_update_user_email_already_taken(
    startup_and_shutdown_uvicorn_server: None, auth_context: AuthContext
) -> None:
    async with temporary_user() as (user_created, headers):
        response = await send_auth_request(
            HTTPMethod.PUT,
            f"users/{user_created.id}",
            auth_context.model_copy(update={"user": user_created, "headers": headers}),
            json={"name": "name", "email": auth_context.user.email.upper()},
        )

    assert response == {"detail": "This email is already taken"}


@pytest.mark.asyncio(loop_scope="session")
async def test_users_cannot_access_each_other(
    startup_and_shutdown_uvicorn_server: None, auth_context: AuthContext
) -> None:
    async with temporary_user() as (user_created, _):
        responses = [
            await send_auth_request(HTTPMethod.GET, f"users/{user_created.id}", auth_context),
            await send_auth_request(
                HTTPMethod.PUT,
                f"users/{user_created.id}",
                auth_context,
                json={"name": "Hijacked", "email": "hijacked@example.org"},
            ),
            await send_auth_request(
                HTTPMethod.PUT,
                f"users/{user_created.id}/password",
                auth_context,
                json={"current_password": "mypassword", "password": "hijacked-pass-phrase-42"},
            ),
        ]

    assert responses == [{"detail": "You can only manage your own account"}] * 3


@pytest.mark.asyncio(loop_scope="session")
async def test_update_user_password(
    conn: AsyncConnection, startup_and_shutdown_uvicorn_server: None, auth_context: AuthContext
) -> None:
    async with temporary_user() as (user_created, headers):
        body = {"current_password": "some password", "password": "correct-horse-battery-staple"}
        response = await send_auth_request(
            HTTPMethod.PUT,
            f"users/{user_created.id}/password",
            auth_context.model_copy(update={"user": user_created, "headers": headers}),
            json=body,
        )
        updated_user = await fetch_one_parsed_certain(
            conn, User, query=users.select().where(users.c.id == user_created.id)
        )

        assert response.get("success") is True, response
        assert updated_user.password_hash and updated_user.password_hash.startswith("$argon2id$")
        assert verify_password(body["password"], updated_user.password_hash)[0]


@pytest.mark.asyncio(loop_scope="session")
async def test_update_user_password_needs_current_password(
    conn: AsyncConnection, startup_and_shutdown_uvicorn_server: None, auth_context: AuthContext
) -> None:
    async with temporary_user() as (user_created, headers):
        body = {"current_password": "wrong password", "password": "correct-horse-battery-staple"}
        response = await send_auth_request(
            HTTPMethod.PUT,
            f"users/{user_created.id}/password",
            auth_context.model_copy(update={"user": user_created, "headers": headers}),
            json=body,
        )
        password_hash = await conn.scalar(
            select(users.c.password_hash).where(users.c.id == user_created.id)
        )

    assert response == {"detail": "The current password is incorrect"}
    assert password_hash == user_created.password_hash


@pytest.mark.asyncio(loop_scope="session")
async def test_email_with_wildcards_is_not_a_pattern(
    conn: AsyncConnection, startup_and_shutdown_uvicorn_server: None, auth_context: AuthContext
) -> None:
    """
    Regression test: emails were looked up with `ILIKE`, so a token of `%@example.org` belonged to
    whichever account with that domain came first.
    """
    victim_domain = auth_context.user.email.split("@")[1]
    response = await send_request(
        HTTPMethod.POST,
        "users/register",
        None,
        {"name": "Mallory", "email": f"%@{victim_domain}", "password": "a-long-passphrase-42"},
    )
    assert "data" in response, response
    headers = {"Authorization": f"Bearer {response['data']['access_token']}"}

    try:
        me = await send_request(HTTPMethod.GET, "users/me", None, None, headers)
        login = await send_request(
            HTTPMethod.POST,
            "token",
            {"username": f"%@{victim_domain}", "password": "a-long-passphrase-42"},
        )
    finally:
        await delete_user(conn, response["data"]["user_id"])

    assert me["data"]["id"] == response["data"]["user_id"] != auth_context.user.id
    assert login["user_id"] == response["data"]["user_id"]


@pytest.mark.asyncio(loop_scope="session")
async def test_update_user_password_signs_out_other_sessions(
    startup_and_shutdown_uvicorn_server: None, auth_context: AuthContext
) -> None:
    async with (
        temporary_user() as (user_created, headers),
        aiohttp.ClientSession() as session,
    ):
        response = await session.put(
            f"{get_root_uvicorn_url()}users/{user_created.id}/password",
            json={"current_password": "some password", "password": "correct-horse-battery-staple"},
            headers=headers,
        )
        new_session = {"Authorization": f"Bearer {response.cookies[SESSION_COOKIE].value}"}
        # The token the password was changed with stands for every other session.
        context = auth_context.model_copy(update={"user": user_created, "headers": headers})
        other_session = await send_auth_request(HTTPMethod.GET, "users/me", context)
        this_session = await send_auth_request(
            HTTPMethod.GET, "users/me", context.model_copy(update={"headers": new_session})
        )

    assert response.status == 200
    assert other_session == {"detail": "Could not validate credentials"}
    assert this_session["data"]["id"] == user_created.id
