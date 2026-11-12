from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from http import HTTPMethod

import pytest
from heliclockter import datetime_utc

from bracket.database import engine
from bracket.models.db.account import UserAccountType
from bracket.models.db.user import User, UserInsertable
from bracket.sql.users import create_user, delete_user
from bracket.utils.security import hash_password
from tests.integration_tests.api.shared import send_auth_request, send_tournament_request
from tests.integration_tests.mocks import get_mock_token
from tests.integration_tests.models import AuthContext


@asynccontextmanager
async def helper_account(auth_context: AuthContext) -> AsyncIterator[tuple[User, AuthContext]]:
    """A second organizer account, and the auth context that signs requests as them."""
    async with engine.begin() as conn:
        helper = await create_user(
            conn,
            UserInsertable(
                email="helper@example.org",
                password_hash=hash_password("some password"),
                name="Helper",
                created=datetime_utc.now(),
                account_type=UserAccountType.REGULAR,
            ),
        )
    try:
        headers = {"Authorization": f"Bearer {get_mock_token(helper)}"}
        yield helper, auth_context.model_copy(update={"headers": headers})
    finally:
        async with engine.begin() as conn:
            await delete_user(conn, helper.id)


@pytest.mark.asyncio(loop_scope="session")
async def test_owner_adds_and_removes_an_organizer(
    startup_and_shutdown_uvicorn_server: None, auth_context: AuthContext
) -> None:
    """Organizers don't have to share a login: the owner lets other accounts run the event."""
    members = f"clubs/{auth_context.club.id}/members"

    async with helper_account(auth_context) as (helper, as_helper):
        before = await send_tournament_request(HTTPMethod.GET, "teams", as_helper)
        unknown = await send_auth_request(
            HTTPMethod.POST, members, auth_context, json={"email": "nobody@example.org"}
        )
        added = await send_auth_request(
            HTTPMethod.POST, members, auth_context, json={"email": "Helper@Example.org"}
        )
        twice = await send_auth_request(
            HTTPMethod.POST, members, auth_context, json={"email": helper.email}
        )

        can_manage = await send_tournament_request(
            HTTPMethod.POST,
            "teams",
            as_helper,
            json={"name": "T", "active": True, "player_ids": []},
        )
        sees_members = await send_auth_request(HTTPMethod.GET, members, as_helper)
        # Running the event's tournaments is all a helper does.
        refused = [
            await send_auth_request(
                HTTPMethod.POST, members, as_helper, json={"email": auth_context.user.email}
            ),
            await send_auth_request(
                HTTPMethod.PUT, f"clubs/{auth_context.club.id}", as_helper, json={"name": "Mine"}
            ),
            await send_auth_request(HTTPMethod.DELETE, f"clubs/{auth_context.club.id}", as_helper),
            await send_auth_request(
                HTTPMethod.DELETE, f"{members}/{auth_context.user.id}", as_helper
            ),
        ]
        await send_tournament_request(
            HTTPMethod.DELETE, f"teams/{can_manage['data']['id']}", auth_context
        )

        removed = await send_auth_request(HTTPMethod.DELETE, f"{members}/{helper.id}", auth_context)
        after = await send_tournament_request(HTTPMethod.GET, "teams", as_helper)

    # The fixture's tournament is public, so anyone can read it. Managing it is what is granted.
    assert "data" in before and "data" in after
    assert unknown == {"detail": "No account has this email address. They need an account first."}
    assert [(member["name"], member["relation"]) for member in added["data"]] == [
        (auth_context.user.name, "OWNER"),
        ("Helper", "COLLABORATOR"),
    ]
    assert twice == {"detail": "Helper already helps run this event"}
    assert can_manage["data"]["name"] == "T"
    assert len(sees_members["data"]) == 2
    assert refused == [
        {"detail": "Only the owner of this event can do that"},
        {"detail": "Only the owner of this event can do that"},
        {"detail": "Only the owner of this event can do that"},
        {"detail": "The owner can't be removed from the event. Delete the event instead."},
    ]
    assert [member["relation"] for member in removed["data"]] == ["OWNER"]


@pytest.mark.asyncio(loop_scope="session")
async def test_event_names_are_unique_per_organizer(
    startup_and_shutdown_uvicorn_server: None, auth_context: AuthContext
) -> None:
    """Two organizers can both run a "LAN party", and neither learns what the other named theirs."""
    async with helper_account(auth_context) as (_, as_helper):
        same_name_other_owner = await send_auth_request(
            HTTPMethod.POST, "clubs", as_helper, json={"name": auth_context.club.name}
        )
        same_name_same_owner = await send_auth_request(
            HTTPMethod.POST, "clubs", as_helper, json={"name": auth_context.club.name.upper()}
        )
        await send_auth_request(
            HTTPMethod.DELETE, f"clubs/{same_name_other_owner['data']['id']}", as_helper
        )

    assert same_name_other_owner["data"]["name"] == auth_context.club.name
    assert same_name_same_owner == {"detail": "You already have an event with this name"}
