from http import HTTPMethod
from uuid import uuid4

import pytest
from sqlalchemy.ext.asyncio import AsyncConnection

from bracket.models.db.club import ClubInsertable
from bracket.models.db.user_x_club import UserXClubInsertable, UserXClubRelation
from bracket.sql.clubs import get_clubs_for_user_id, sql_delete_club
from bracket.utils.dummy_records import DUMMY_CLUB, DUMMY_MOCK_TIME
from tests.integration_tests.api.shared import send_auth_request
from tests.integration_tests.models import AuthContext
from tests.integration_tests.sql import inserted_club, inserted_user_x_club


def unique_club() -> ClubInsertable:
    # Club names are unique, and the auth context already has a club named like `DUMMY_CLUB`.
    return DUMMY_CLUB.model_copy(update={"name": f"Club {uuid4()}"})


@pytest.mark.asyncio(loop_scope="session")
async def test_clubs_endpoint(
    startup_and_shutdown_uvicorn_server: None, auth_context: AuthContext
) -> None:
    assert await send_auth_request(HTTPMethod.GET, "clubs", auth_context, {}) == {
        "data": [
            {
                "created": DUMMY_MOCK_TIME.isoformat().replace("+00:00", "Z"),
                "id": auth_context.club.id,
                "name": "Some Cool Club",
            }
        ],
    }


@pytest.mark.asyncio(loop_scope="session")
async def test_create_club(
    conn: AsyncConnection, startup_and_shutdown_uvicorn_server: None, auth_context: AuthContext
) -> None:
    payload = {"name": f"New club {uuid4()}"}
    response = await send_auth_request(HTTPMethod.POST, "clubs", auth_context, json=payload)

    clubs = await get_clubs_for_user_id(conn, auth_context.user.id)
    club_id = response["data"]["id"]

    await sql_delete_club(conn, club_id)

    assert len(clubs) == 2
    assert response["data"]["name"] == payload["name"]


@pytest.mark.asyncio(loop_scope="session")
async def test_update_club(
    conn: AsyncConnection, startup_and_shutdown_uvicorn_server: None, auth_context: AuthContext
) -> None:
    payload = {"name": f"Renamed club {uuid4()}"}
    async with inserted_club(unique_club()) as club_inserted:
        async with inserted_user_x_club(
            UserXClubInsertable(
                user_id=auth_context.user.id,
                club_id=club_inserted.id,
                relation=UserXClubRelation.OWNER,
            )
        ):
            response = await send_auth_request(
                HTTPMethod.PUT, f"clubs/{club_inserted.id}", auth_context, json=payload
            )

    clubs = await get_clubs_for_user_id(conn, auth_context.user.id)
    await sql_delete_club(conn, response["data"]["id"])

    assert len(clubs) == 1
    assert response["data"]["name"] == payload["name"]


@pytest.mark.asyncio(loop_scope="session")
async def test_delete_club(
    startup_and_shutdown_uvicorn_server: None, auth_context: AuthContext
) -> None:
    async with inserted_club(unique_club()) as club_inserted:
        async with inserted_user_x_club(
            UserXClubInsertable(
                user_id=auth_context.user.id,
                club_id=club_inserted.id,
                relation=UserXClubRelation.OWNER,
            )
        ):
            response = await send_auth_request(
                HTTPMethod.DELETE, f"clubs/{club_inserted.id}", auth_context
            )
            assert response["success"] is True
