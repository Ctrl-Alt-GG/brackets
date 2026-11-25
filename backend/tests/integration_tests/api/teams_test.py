from http import HTTPMethod

import aiofiles.os
import aiohttp
import pytest

from bracket.models.db.player import PlayerInsertable
from bracket.utils.types import JsonDict
from bracket.utils.uploads import UploadFolder, build_upload_path
from tests.dummy_records import DUMMY_MOCK_TIME, DUMMY_PLAYER1, DUMMY_TEAM1, DUMMY_TOURNAMENT
from tests.integration_tests.api.shared import (
    SUCCESS_RESPONSE,
    get_root_uvicorn_url,
    send_auth_request,
    send_request,
    send_tournament_request,
)
from tests.integration_tests.models import AuthContext
from tests.integration_tests.sql import (
    created_teams_and_players_removed,
    inserted_player,
    inserted_team,
    inserted_tournament,
)
from tests.integration_tests.uploads import wait_until_removed

CREATED = DUMMY_MOCK_TIME.isoformat().replace("+00:00", "Z")


def player(name: str) -> PlayerInsertable:
    return DUMMY_PLAYER1.model_copy(update={"name": name})


@pytest.mark.asyncio(loop_scope="session")
async def test_teams_come_with_their_rosters_and_tournaments(
    startup_and_shutdown_uvicorn_server: None, auth_context: AuthContext
) -> None:
    async with (
        inserted_team(DUMMY_TEAM1, auth_context.tournament.id) as team,
        inserted_player(player("Amy")) as amy,
    ):
        await send_auth_request(
            HTTPMethod.PUT,
            f"teams/{team.id}",
            auth_context,
            json={"name": "Team 1", "members": [{"player_id": amy.id, "active": False}]},
        )
        response = await send_auth_request(HTTPMethod.GET, "teams", auth_context)
        anonymous = await send_request(HTTPMethod.GET, "teams")

    [listed] = [listed for listed in response["data"] if listed["id"] == team.id]
    assert listed == {
        "id": team.id,
        "name": "Team 1",
        "created": CREATED,
        "logo_path": None,
        "members": [{"player": {"id": amy.id, "name": "Amy", "created": CREATED}, "active": False}],
        "participations": [
            {
                "tournament_id": auth_context.tournament.id,
                "tournament_name": auth_context.tournament.name,
                "tournament_status": "OPEN",
                "active": True,
            }
        ],
    }
    assert anonymous == {"detail": "Could not validate credentials"}


@pytest.mark.asyncio(loop_scope="session")
async def test_create_update_and_delete_a_team(
    startup_and_shutdown_uvicorn_server: None, auth_context: AuthContext
) -> None:
    async with inserted_player(player("Max")) as max_, inserted_player(player("Zed")) as zed:
        created = await send_auth_request(
            HTTPMethod.POST,
            "teams",
            auth_context,
            json={"name": "New team", "members": [{"player_id": max_.id}]},
        )
        team_id = created["data"]["id"]
        updated = await send_auth_request(
            HTTPMethod.PUT,
            f"teams/{team_id}",
            auth_context,
            json={
                "name": "Renamed",
                "members": [
                    {"player_id": max_.id, "active": False},
                    {"player_id": zed.id, "active": True},
                ],
            },
        )
        deleted = await send_auth_request(HTTPMethod.DELETE, f"teams/{team_id}", auth_context)
        gone = await send_auth_request(HTTPMethod.GET, "teams", auth_context)

    assert [
        (member["player"]["name"], member["active"]) for member in created["data"]["members"]
    ] == [("Max", True)]
    assert updated["data"]["name"] == "Renamed"
    assert [
        (member["player"]["name"], member["active"]) for member in updated["data"]["members"]
    ] == [("Max", False), ("Zed", True)]
    assert deleted == SUCCESS_RESPONSE
    assert team_id not in [team["id"] for team in gone["data"]]


@pytest.mark.asyncio(loop_scope="session")
@pytest.mark.parametrize(
    ("members", "error"),
    [
        ([{"player_id": -1}], {"detail": "There is no player with the ID [-1]"}),
        (
            [{"player_id": -1}, {"player_id": -1, "active": False}],
            "A player can be in a team's roster once",
        ),
    ],
)
async def test_invalid_rosters_are_refused(
    startup_and_shutdown_uvicorn_server: None,
    auth_context: AuthContext,
    members: list[JsonDict],
    error: str | JsonDict,
) -> None:
    async with created_teams_and_players_removed():
        response = await send_auth_request(
            HTTPMethod.POST, "teams", auth_context, json={"name": "Team", "members": members}
        )
    if isinstance(error, dict):
        assert response == error
    else:
        assert [detail["msg"] for detail in response["detail"]] == [f"Value error, {error}"]


@pytest.mark.asyncio(loop_scope="session")
async def test_a_team_that_takes_part_is_not_deleted(
    startup_and_shutdown_uvicorn_server: None, auth_context: AuthContext
) -> None:
    async with inserted_team(DUMMY_TEAM1, auth_context.tournament.id) as team:
        response = await send_auth_request(HTTPMethod.DELETE, f"teams/{team.id}", auth_context)

    assert response == {
        "detail": (
            f"Team 1 takes part in {auth_context.tournament.name}. Remove it from those "
            "tournaments first."
        )
    }


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

    async with inserted_team(DUMMY_TEAM1) as team:
        response = await send_request(
            HTTPMethod.POST, f"teams/{team.id}/logo", body=data, headers=auth_context.headers
        )
        assert response["data"]["logo_path"], f"Response: {response}"
        logo_path = build_upload_path(UploadFolder.TEAM_LOGOS, response["data"]["logo_path"])
        assert await aiofiles.os.path.exists(logo_path)

        # Visitors see the logo on the Details pages of the team's tournaments.
        async with aiohttp.ClientSession() as client:
            async with client.get(f"{get_root_uvicorn_url()}teams/{team.id}/logo") as logo:
                assert logo.status == 200
                assert logo.content_type == "image/png"

        response = await send_request(
            HTTPMethod.POST,
            f"teams/{team.id}/logo",
            body=aiohttp.FormData(),
            headers=auth_context.headers,
        )
        assert response["data"]["logo_path"] is None, f"Response: {response}"
        await wait_until_removed(logo_path)


@pytest.mark.asyncio(loop_scope="session")
async def test_the_teams_that_take_part(
    startup_and_shutdown_uvicorn_server: None, auth_context: AuthContext
) -> None:
    async with (
        inserted_team(DUMMY_TEAM1, auth_context.tournament.id) as team,
        inserted_team(DUMMY_TEAM1.model_copy(update={"name": "Not taking part"})),
    ):
        response = await send_tournament_request(HTTPMethod.GET, "teams", auth_context)

    assert response == {
        "data": {
            "teams": [
                {
                    "id": team.id,
                    "name": "Team 1",
                    "created": CREATED,
                    "logo_path": None,
                    "tournament_id": auth_context.tournament.id,
                    "active": True,
                    "players": [],
                    "elo_score": "1200.0",
                    "swiss_score": "0.0",
                    "wins": 0,
                    "draws": 0,
                    "losses": 0,
                }
            ],
            "count": 1,
        },
    }


@pytest.mark.asyncio(loop_scope="session")
async def test_teams_join_change_and_leave_a_tournament(
    startup_and_shutdown_uvicorn_server: None, auth_context: AuthContext
) -> None:
    async with inserted_team(DUMMY_TEAM1) as team:
        joined = await send_tournament_request(
            HTTPMethod.POST, "teams", auth_context, json={"team_ids": [team.id]}
        )
        twice = await send_tournament_request(
            HTTPMethod.POST, "teams", auth_context, json={"team_ids": [team.id]}
        )
        unknown = await send_tournament_request(
            HTTPMethod.POST, "teams", auth_context, json={"team_ids": [-1]}
        )
        inactive = await send_tournament_request(
            HTTPMethod.PUT, f"teams/{team.id}", auth_context, json={"active": False}
        )
        left = await send_tournament_request(HTTPMethod.DELETE, f"teams/{team.id}", auth_context)
        after = await send_tournament_request(HTTPMethod.GET, "teams", auth_context)

    assert joined == SUCCESS_RESPONSE
    assert twice == {"detail": "Some of these teams already take part in this tournament"}
    assert unknown == {"detail": "There is no team with the ID [-1]"}
    assert (inactive["data"]["id"], inactive["data"]["active"]) == (team.id, False)
    assert left == SUCCESS_RESPONSE
    assert after["data"]["count"] == 0


@pytest.mark.asyncio(loop_scope="session")
async def test_create_teams_from_a_list(
    startup_and_shutdown_uvicorn_server: None, auth_context: AuthContext
) -> None:
    """A listed player whose name is taken joins as that player, whatever the case."""
    async with created_teams_and_players_removed(), inserted_player(player("Amy")) as amy:
        response = await send_tournament_request(
            HTTPMethod.POST,
            "teams_multi",
            auth_context,
            json={"names": "Team -1,AMY, Player 43\n\nTeam -2,"},
        )
        teams = await send_tournament_request(HTTPMethod.GET, "teams", auth_context)

    assert response == SUCCESS_RESPONSE
    lineups = {team["name"]: team["players"] for team in teams["data"]["teams"]}
    assert {name: [player["name"] for player in players] for name, players in lineups.items()} == {
        "Team -1": ["Amy", "Player 43"],
        "Team -2": [],
    }
    assert lineups["Team -1"][0]["id"] == amy.id


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
    async with created_teams_and_players_removed():
        response = await send_tournament_request(
            HTTPMethod.POST, "teams_multi", auth_context, json={"names": names}
        )

    assert [detail["msg"] for detail in response["detail"]] == [f"Value error, {error}"]


@pytest.mark.asyncio(loop_scope="session")
async def test_a_name_that_several_players_have_is_refused(
    startup_and_shutdown_uvicorn_server: None, auth_context: AuthContext
) -> None:
    async with (
        created_teams_and_players_removed(),
        inserted_player(player("Twin")),
        inserted_player(player("twin")),
    ):
        response = await send_tournament_request(
            HTTPMethod.POST, "teams_multi", auth_context, json={"names": "Twins,Twin"}
        )
        teams = await send_tournament_request(HTTPMethod.GET, "teams", auth_context)

    assert response == {
        "detail": (
            "Several players are called Twin. Add that player to the team in Teams and players, "
            "where you can choose which of them it is."
        )
    }
    assert teams["data"]["count"] == 0


@pytest.mark.asyncio(loop_scope="session")
async def test_a_team_of_another_tournament_is_not_found_here(
    startup_and_shutdown_uvicorn_server: None, auth_context: AuthContext
) -> None:
    """Regression test: a team of tournament B can't be changed through tournament A's URL."""
    async with (
        inserted_tournament(
            DUMMY_TOURNAMENT.model_copy(update={"dashboard_endpoint": None}), auth_context.user.id
        ) as other_tournament,
        inserted_team(DUMMY_TEAM1, other_tournament.id) as other_team,
    ):
        response = await send_tournament_request(
            HTTPMethod.PUT, f"teams/{other_team.id}", auth_context, json={"active": False}
        )

    assert response == {"detail": f"No team with id {other_team.id} takes part in this tournament"}


@pytest.mark.asyncio(loop_scope="session")
@pytest.mark.parametrize(
    ("query", "parameter"),
    [
        ("limit=0", "limit"),
        ("limit=501", "limit"),
        ("offset=-1", "offset"),
        ("sort_by=email", "sort_by"),
    ],
)
async def test_invalid_pages_are_refused(
    startup_and_shutdown_uvicorn_server: None, auth_context: AuthContext, query: str, parameter: str
) -> None:
    response = await send_tournament_request(HTTPMethod.GET, f"teams?{query}", auth_context)
    assert [error["loc"] for error in response["detail"]] == [["query", parameter]]
