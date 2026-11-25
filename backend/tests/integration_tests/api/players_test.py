from http import HTTPMethod

import pytest

from tests.dummy_records import DUMMY_MOCK_TIME, DUMMY_PLAYER1, DUMMY_TEAM1
from tests.integration_tests.api.shared import (
    SUCCESS_RESPONSE,
    send_auth_request,
    send_tournament_request,
)
from tests.integration_tests.models import AuthContext
from tests.integration_tests.sql import (
    created_teams_and_players_removed,
    inserted_player,
    inserted_player_in_team,
    inserted_team,
)

CREATED = DUMMY_MOCK_TIME.isoformat().replace("+00:00", "Z")


@pytest.mark.asyncio(loop_scope="session")
async def test_a_tournament_has_the_players_who_play_for_its_teams(
    startup_and_shutdown_uvicorn_server: None, auth_context: AuthContext
) -> None:
    async with (
        inserted_team(DUMMY_TEAM1, auth_context.tournament.id) as team,
        inserted_player_in_team(DUMMY_PLAYER1, team.id) as playing,
        inserted_player_in_team(
            DUMMY_PLAYER1.model_copy(update={"name": "On the bench"}), team.id, active=False
        ),
        inserted_player(DUMMY_PLAYER1.model_copy(update={"name": "In no team"})),
    ):
        response = await send_tournament_request(HTTPMethod.GET, "players", auth_context)

    assert response == {
        "data": {
            "players": [
                {
                    "created": CREATED,
                    "id": playing.id,
                    "name": "Player 01",
                    "team_id": team.id,
                    "elo_score": "1200",
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
async def test_create_rename_and_delete_players(
    startup_and_shutdown_uvicorn_server: None, auth_context: AuthContext
) -> None:
    async with created_teams_and_players_removed():
        created = await send_auth_request(
            HTTPMethod.POST, "players", auth_context, json={"name": "  Some name "}
        )
        player_id = created["data"]["id"]
        renamed = await send_auth_request(
            HTTPMethod.PUT, f"players/{player_id}", auth_context, json={"name": "New name"}
        )
        deleted = await send_auth_request(HTTPMethod.DELETE, f"players/{player_id}", auth_context)
        unknown = await send_auth_request(
            HTTPMethod.PUT, f"players/{player_id}", auth_context, json={"name": "Gone"}
        )
        players = await send_auth_request(HTTPMethod.GET, "players", auth_context)

    assert created["data"]["name"] == "Some name"
    assert renamed["data"] == {**created["data"], "name": "New name"}
    assert deleted == SUCCESS_RESPONSE
    assert unknown == {"detail": f"Could not find player with id {player_id}"}
    assert player_id not in [player["id"] for player in players["data"]]


@pytest.mark.asyncio(loop_scope="session")
async def test_create_players_from_a_list(
    startup_and_shutdown_uvicorn_server: None, auth_context: AuthContext
) -> None:
    async with created_teams_and_players_removed():
        response = await send_auth_request(
            HTTPMethod.POST,
            "players_multi",
            auth_context,
            json={"names": "Player x\n  Player y  \n\n"},
        )
        players = await send_auth_request(HTTPMethod.GET, "players", auth_context)

    assert response == SUCCESS_RESPONSE
    assert {"Player x", "Player y"} <= {player["name"] for player in players["data"]}


@pytest.mark.asyncio(loop_scope="session")
async def test_create_players_with_too_long_name(
    startup_and_shutdown_uvicorn_server: None, auth_context: AuthContext
) -> None:
    async with created_teams_and_players_removed():
        response = await send_auth_request(
            HTTPMethod.POST, "players_multi", auth_context, json={"names": f"Player x\n{'y' * 31}"}
        )

    assert response["detail"][0]["msg"] == (
        f'Value error, "{"y" * 31}" is longer than the 30 characters a name can have'
    )


@pytest.mark.asyncio(loop_scope="session")
async def test_a_deleted_player_leaves_their_teams_and_lineups(
    startup_and_shutdown_uvicorn_server: None, auth_context: AuthContext
) -> None:
    async with (
        inserted_team(DUMMY_TEAM1, auth_context.tournament.id) as team,
        inserted_player_in_team(DUMMY_PLAYER1, team.id) as player,
    ):
        deleted = await send_auth_request(HTTPMethod.DELETE, f"players/{player.id}", auth_context)
        teams = await send_tournament_request(HTTPMethod.GET, "teams", auth_context)

    assert deleted == SUCCESS_RESPONSE
    assert teams["data"]["teams"][0]["players"] == []
