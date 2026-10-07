from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from http import HTTPMethod

import pytest
from heliclockter import datetime_utc
from sqlalchemy.ext.asyncio import AsyncConnection

from bracket.database import engine
from bracket.models.db.account import UserAccountType
from bracket.models.db.user import User, UserInsertable
from bracket.schema import users
from bracket.sql.users import create_user, delete_user, get_user_by_id
from bracket.utils.db import fetch_one_parsed_certain
from bracket.utils.security import hash_password
from bracket.utils.types import assert_some
from tests.integration_tests.api.shared import send_auth_request, send_request
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
        headers = {"Authorization": f"Bearer {get_mock_token(user_created.email)}"}
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
async def test_update_user_password(
    conn: AsyncConnection, startup_and_shutdown_uvicorn_server: None, auth_context: AuthContext
) -> None:
    async with temporary_user() as (user_created, headers):
        body = {"password": "correct-horse-battery-staple"}
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
        assert auth_context.user != updated_user.password_hash
