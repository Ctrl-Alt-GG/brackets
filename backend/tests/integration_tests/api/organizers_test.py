from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from http import HTTPMethod

import pytest
from heliclockter import datetime_utc
from sqlalchemy.ext.asyncio import AsyncSession

from bracket.database import engine
from bracket.models.db.user import User, UserInsertable
from bracket.models.enums import UserAccountType
from bracket.sql.organizers import get_organizers
from bracket.sql.tournaments import sql_get_tournament
from bracket.sql.users import create_user, delete_user
from bracket.utils.security import hash_password
from tests.integration_tests.api.shared import send_request, send_tournament_request
from tests.integration_tests.mocks import get_mock_token
from tests.integration_tests.models import AuthContext


@asynccontextmanager
async def helper_account(auth_context: AuthContext) -> AsyncIterator[tuple[User, AuthContext]]:
    """A second organizer account, and the auth context that signs requests as them."""
    async with AsyncSession(engine) as session, session.begin():
        helper = await create_user(
            session,
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
        async with AsyncSession(engine) as session, session.begin():
            await delete_user(session, helper.id)


@pytest.mark.asyncio(loop_scope="session")
async def test_owner_adds_and_removes_an_organizer(
    startup_and_shutdown_uvicorn_server: None, auth_context: AuthContext
) -> None:
    """Organizers don't have to share a login: the owner lets other accounts run the tournament."""
    async with helper_account(auth_context) as (helper, as_helper):
        before = await send_tournament_request(HTTPMethod.GET, "workspace", as_helper)
        unknown = await send_tournament_request(
            HTTPMethod.POST, "organizers", auth_context, json={"email": "nobody@example.org"}
        )
        added = await send_tournament_request(
            HTTPMethod.POST, "organizers", auth_context, json={"email": "Helper@Example.org"}
        )
        twice = await send_tournament_request(
            HTTPMethod.POST, "organizers", auth_context, json={"email": helper.email}
        )

        can_manage = await send_tournament_request(HTTPMethod.GET, "workspace", as_helper)
        sees_organizers = await send_tournament_request(HTTPMethod.GET, "organizers", as_helper)
        # Running the tournament is all a helper does.
        refused = [
            await send_tournament_request(
                HTTPMethod.POST, "organizers", as_helper, json={"email": auth_context.user.email}
            ),
            await send_tournament_request(
                HTTPMethod.PUT, "owner", as_helper, json={"user_id": helper.id}
            ),
            await send_request(
                HTTPMethod.DELETE,
                f"tournaments/{auth_context.tournament.id}",
                headers=as_helper.headers,
            ),
            await send_tournament_request(
                HTTPMethod.DELETE, f"organizers/{auth_context.user.id}", as_helper
            ),
        ]

        removed = await send_tournament_request(
            HTTPMethod.DELETE, f"organizers/{helper.id}", auth_context
        )
        after = await send_tournament_request(HTTPMethod.GET, "workspace", as_helper)

    assert before == after == {"detail": "You don't have access to this tournament"}
    assert unknown == {"detail": "No account has this email address. They need an account first."}
    assert [(organizer["name"], organizer["role"]) for organizer in added["data"]] == [
        (auth_context.user.name, "OWNER"),
        ("Helper", "COLLABORATOR"),
    ]
    assert twice == {"detail": "Helper already helps run this tournament"}
    assert can_manage["data"]["tournament"]["id"] == auth_context.tournament.id
    assert len(sees_organizers["data"]) == 2
    assert refused == [
        {"detail": "Only the owner of this tournament can do that"},
        {"detail": "Only the owner of this tournament can do that"},
        {"detail": "Only the owner of this tournament can do that"},
        {"detail": "The owner can't leave the tournament. Make someone else the owner first."},
    ]
    assert [organizer["role"] for organizer in removed["data"]] == ["OWNER"]


@pytest.mark.asyncio(loop_scope="session")
async def test_the_owner_hands_the_tournament_over(
    startup_and_shutdown_uvicorn_server: None, auth_context: AuthContext
) -> None:
    """An owner who leaves the organizing team hands the tournament over to someone who stays."""
    async with helper_account(auth_context) as (helper, as_helper):
        not_an_organizer = await send_tournament_request(
            HTTPMethod.PUT, "owner", auth_context, json={"user_id": helper.id}
        )
        await send_tournament_request(
            HTTPMethod.POST, "organizers", auth_context, json={"email": helper.email}
        )
        by_helper = await send_tournament_request(
            HTTPMethod.PUT, "owner", as_helper, json={"user_id": helper.id}
        )
        handed_over = await send_tournament_request(
            HTTPMethod.PUT, "owner", auth_context, json={"user_id": helper.id}
        )
        add_by_former_owner = await send_tournament_request(
            HTTPMethod.POST, "organizers", auth_context, json={"email": "x@example.org"}
        )
        handed_back = await send_tournament_request(
            HTTPMethod.PUT, "owner", as_helper, json={"user_id": auth_context.user.id}
        )
        removed = await send_tournament_request(
            HTTPMethod.DELETE, f"organizers/{helper.id}", auth_context
        )

    assert not_an_organizer == {
        "detail": "Only an organizer of the tournament can become its owner. Add them first."
    }
    assert by_helper == {"detail": "Only the owner of this tournament can do that"}
    assert [(organizer["name"], organizer["role"]) for organizer in handed_over["data"]] == [
        ("Helper", "OWNER"),
        (auth_context.user.name, "COLLABORATOR"),
    ]
    assert add_by_former_owner == {"detail": "Only the owner of this tournament can do that"}
    assert [organizer["role"] for organizer in handed_back["data"]] == ["OWNER", "COLLABORATOR"]
    assert [organizer["role"] for organizer in removed["data"]] == ["OWNER"]


@pytest.mark.asyncio(loop_scope="session")
async def test_a_helper_leaves_and_deleted_accounts_lose_access(
    startup_and_shutdown_uvicorn_server: None, auth_context: AuthContext
) -> None:
    """Anyone who helps can leave, and an account that is deleted stops running tournaments."""
    async with helper_account(auth_context) as (helper, as_helper):
        await send_tournament_request(
            HTTPMethod.POST, "organizers", auth_context, json={"email": helper.email}
        )
        left = await send_tournament_request(
            HTTPMethod.DELETE, f"organizers/{helper.id}", as_helper
        )
        await send_tournament_request(
            HTTPMethod.POST, "organizers", auth_context, json={"email": helper.email}
        )

    # The helper's account is gone now; the tournament and its owner stay.
    async with AsyncSession(engine) as session:
        organizers = await get_organizers(session, auth_context.tournament.id)
        tournament = await sql_get_tournament(session, auth_context.tournament.id)

    assert [organizer["role"] for organizer in left["data"]] == ["OWNER"]
    assert [organizer.user_id for organizer in organizers] == [auth_context.user.id]
    assert tournament.id == auth_context.tournament.id
