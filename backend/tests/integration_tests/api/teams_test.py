from http import HTTPMethod

import aiofiles.os
import aiohttp
import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from bracket import orm
from bracket.database import engine
from bracket.models.db.team import Team
from bracket.utils.dummy_records import DUMMY_MOCK_TIME, DUMMY_TEAM1, DUMMY_TOURNAMENT
from bracket.utils.uploads import build_upload_path
from tests.integration_tests.api.shared import (
    SUCCESS_RESPONSE,
    send_auth_request,
    send_tournament_request,
)
from tests.integration_tests.models import AuthContext
from tests.integration_tests.sql import (
    assert_row_count_and_clear,
    inserted_team,
    inserted_tournament,
)
from tests.integration_tests.uploads import wait_until_removed


@pytest.mark.asyncio(loop_scope="session")
async def test_teams_endpoint(
    startup_and_shutdown_uvicorn_server: None, auth_context: AuthContext
) -> None:
    async with inserted_team(
        DUMMY_TEAM1.model_copy(update={"tournament_id": auth_context.tournament.id})
    ) as team_inserted:
        assert await send_tournament_request(HTTPMethod.GET, "teams", auth_context, {}) == {
            "data": {
                "teams": [
                    {
                        "active": True,
                        "created": DUMMY_MOCK_TIME.isoformat().replace("+00:00", "Z"),
                        "id": team_inserted.id,
                        "name": "Team 1",
                        "players": [],
                        "tournament_id": team_inserted.tournament_id,
                        "elo_score": "1200.0",
                        "swiss_score": "0.0",
                        "wins": 0,
                        "draws": 0,
                        "losses": 0,
                        "logo_path": None,
                    }
                ],
                "count": 1,
            },
        }


@pytest.mark.asyncio(loop_scope="session")
async def test_create_team(
    startup_and_shutdown_uvicorn_server: None, auth_context: AuthContext
) -> None:
    body = {"name": "Some new name", "active": True, "player_ids": []}
    response = await send_tournament_request(HTTPMethod.POST, "teams", auth_context, None, body)
    assert response["data"]["name"] == body["name"]
    await assert_row_count_and_clear(orm.Team, 1)


@pytest.mark.asyncio(loop_scope="session")
async def test_create_teams(
    startup_and_shutdown_uvicorn_server: None, auth_context: AuthContext
) -> None:
    body = {"names": "Team -1,Player 42, Player 43\n\nTeam -2,", "active": True}
    response = await send_tournament_request(
        HTTPMethod.POST, "teams_multi", auth_context, None, body
    )
    assert response["success"] is True

    async with AsyncSession(engine) as session, session.begin():
        members = (
            await session.execute(
                select(orm.Team.name, orm.Player.name)
                .join(orm.PlayerXTeam, orm.PlayerXTeam.team_id == orm.Team.id)
                .join(orm.Player, orm.Player.id == orm.PlayerXTeam.player_id)
                .order_by(orm.Player.name)
            )
        ).all()
    assert [tuple(member) for member in members] == [
        ("Team -1", "Player 42"),
        ("Team -1", "Player 43"),
    ]

    await assert_row_count_and_clear(orm.PlayerXTeam, 2)
    await assert_row_count_and_clear(orm.Team, 2)
    await assert_row_count_and_clear(orm.Player, 2)


@pytest.mark.asyncio(loop_scope="session")
@pytest.mark.parametrize(
    ("names", "error"),
    [
        (" \n ", "Enter at least one team"),
        (",Player without a team", "Every line needs a team name before its players"),
        (f"Team,{'x' * 31}", f'"{"x" * 31}" is longer than the 30 characters a name can have'),
    ],
)
async def test_create_teams_invalid_names(
    startup_and_shutdown_uvicorn_server: None, auth_context: AuthContext, names: str, error: str
) -> None:
    response = await send_tournament_request(
        HTTPMethod.POST, "teams_multi", auth_context, None, {"names": names, "active": True}
    )

    assert [detail["msg"] for detail in response["detail"]] == [f"Value error, {error}"]
    await assert_row_count_and_clear(orm.Team, 0)


@pytest.mark.asyncio(loop_scope="session")
async def test_delete_team(
    startup_and_shutdown_uvicorn_server: None, auth_context: AuthContext
) -> None:
    async with inserted_team(
        DUMMY_TEAM1.model_copy(update={"tournament_id": auth_context.tournament.id})
    ) as team_inserted:
        assert (
            await send_tournament_request(
                HTTPMethod.DELETE, f"teams/{team_inserted.id}", auth_context, {}
            )
            == SUCCESS_RESPONSE
        )
        await assert_row_count_and_clear(orm.Team, 0)


@pytest.mark.asyncio(loop_scope="session")
async def test_update_team(
    session: AsyncSession, startup_and_shutdown_uvicorn_server: None, auth_context: AuthContext
) -> None:
    body = {"name": "Some new name", "active": True, "player_ids": []}
    async with inserted_team(
        DUMMY_TEAM1.model_copy(update={"tournament_id": auth_context.tournament.id})
    ) as team_inserted:
        response = await send_tournament_request(
            HTTPMethod.PUT, f"teams/{team_inserted.id}", auth_context, None, body
        )
        updated_team = Team.model_validate(
            await session.scalar(
                (select(orm.Team).where(orm.Team.id == team_inserted.id)).execution_options(
                    populate_existing=True
                )
            )
        )
        assert updated_team.name == body["name"]
        assert response["data"]["name"] == body["name"]

        await assert_row_count_and_clear(orm.Team, 1)


@pytest.mark.asyncio(loop_scope="session")
async def test_update_team_invalid_players(
    startup_and_shutdown_uvicorn_server: None, auth_context: AuthContext
) -> None:
    body = {"name": "Some new name", "active": True, "player_ids": [-1]}
    async with inserted_team(
        DUMMY_TEAM1.model_copy(update={"tournament_id": auth_context.tournament.id})
    ) as team_inserted:
        response = await send_tournament_request(
            HTTPMethod.PUT, f"teams/{team_inserted.id}", auth_context, None, body
        )
        assert response == {"detail": "Could not find Player(s) with ID {-1}"}


@pytest.mark.asyncio(loop_scope="session")
async def test_team_upload_and_remove_logo(
    startup_and_shutdown_uvicorn_server: None, auth_context: AuthContext
) -> None:
    test_file_path = "tests/integration_tests/assets/test_logo.png"
    data = aiohttp.FormData()
    data.add_field(
        "file",
        open(test_file_path, "rb"),  # pylint: disable=consider-using-with
        filename="test_logo.png",
        content_type="image/png",
    )

    async with inserted_team(
        DUMMY_TEAM1.model_copy(update={"tournament_id": auth_context.tournament.id})
    ) as team_inserted:
        response = await send_tournament_request(
            method=HTTPMethod.POST,
            endpoint=f"teams/{team_inserted.id}/logo",
            auth_context=auth_context,
            body=data,
        )

        assert response["data"]["logo_path"], f"Response: {response}"
        logo_path = build_upload_path("team-logos", response["data"]["logo_path"])
        assert await aiofiles.os.path.exists(logo_path)

        response = await send_tournament_request(
            method=HTTPMethod.POST,
            endpoint=f"teams/{team_inserted.id}/logo",
            auth_context=auth_context,
            body=aiohttp.FormData(),
        )

        assert response["data"]["logo_path"] is None, f"Response: {response}"
        await wait_until_removed(logo_path)


@pytest.mark.asyncio(loop_scope="session")
async def test_cross_tournament_team_access_denied(
    startup_and_shutdown_uvicorn_server: None, auth_context: AuthContext
) -> None:
    """Regression test: a team from tournament B cannot be accessed via tournament A's URL."""
    async with inserted_tournament(
        DUMMY_TOURNAMENT.model_copy(
            update={"club_id": auth_context.club.id, "dashboard_endpoint": None}
        )
    ) as other_tournament:
        async with inserted_team(
            DUMMY_TEAM1.model_copy(update={"tournament_id": other_tournament.id})
        ) as other_team:
            response = await send_auth_request(
                HTTPMethod.PUT,
                f"tournaments/{auth_context.tournament.id}/teams/{other_team.id}",
                auth_context,
                json={"name": "Hacked", "active": True, "player_ids": []},
            )
            assert response.get("detail") == f"Could not find team with id {other_team.id}"
