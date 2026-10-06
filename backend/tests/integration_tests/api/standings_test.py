from contextlib import AsyncExitStack

import pytest

from bracket.logic.scheduling.builder import build_matches_for_stage_item
from bracket.models.db.match import MatchWithDetailsDefinitive
from bracket.models.db.stage_item import StageItemWithInputsCreate, StageType
from bracket.models.db.stage_item_inputs import (
    StageItemInputCreateBodyFinal,
    StageItemInputFinal,
)
from bracket.sql.shared import sql_delete_stage_item_with_foreign_keys
from bracket.sql.stage_items import get_stage_item, sql_create_stage_item_with_inputs
from bracket.utils.dummy_records import DUMMY_PLAYER1, DUMMY_STAGE1, DUMMY_TEAM1
from bracket.utils.http import HTTPMethod
from tests.integration_tests.api.shared import (
    SUCCESS_RESPONSE,
    send_request,
    send_tournament_request,
)
from tests.integration_tests.models import AuthContext
from tests.integration_tests.sql import inserted_player_in_team, inserted_stage, inserted_team


@pytest.mark.asyncio(loop_scope="session")
async def test_standings_and_player_statistics(
    startup_and_shutdown_uvicorn_server: None, auth_context: AuthContext
) -> None:
    tournament_id = auth_context.tournament.id
    async with AsyncExitStack() as stack:
        stage = await stack.enter_async_context(
            inserted_stage(DUMMY_STAGE1.model_copy(update={"tournament_id": tournament_id}))
        )
        teams = [
            await stack.enter_async_context(
                inserted_team(
                    DUMMY_TEAM1.model_copy(
                        update={"tournament_id": tournament_id, "name": f"Team {index}"}
                    )
                )
            )
            for index in range(1, 4)
        ]
        players = [
            await stack.enter_async_context(
                inserted_player_in_team(
                    DUMMY_PLAYER1.model_copy(
                        update={"tournament_id": tournament_id, "name": f"Player {index}"}
                    ),
                    team.id,
                )
            )
            for index, team in enumerate(teams, start=1)
        ]
        stage_item = await sql_create_stage_item_with_inputs(
            tournament_id,
            StageItemWithInputsCreate(
                stage_id=stage.id,
                name="Group",
                team_count=3,
                type=StageType.ROUND_ROBIN,
                ranking_id=auth_context.ranking.id,
                inputs=[
                    StageItemInputCreateBodyFinal(slot=slot, team_id=team.id)
                    for slot, team in enumerate(teams, start=1)
                ],
            ),
        )
        stack.push_async_callback(sql_delete_stage_item_with_foreign_keys, stage_item.id)
        await build_matches_for_stage_item(stage_item, tournament_id)

        # Team 1 beats team 2 2-1, team 2 beats team 3 3-0, and team 1 vs team 3 isn't played.
        scores = {
            frozenset((teams[0].id, teams[1].id)): {teams[0].id: 2, teams[1].id: 1},
            frozenset((teams[1].id, teams[2].id)): {teams[1].id: 3, teams[2].id: 0},
        }
        for round_ in (await get_stage_item(tournament_id, stage_item.id)).rounds:
            for match in round_.matches:
                assert isinstance(match, MatchWithDetailsDefinitive)
                input1, input2 = match.stage_item_input1, match.stage_item_input2
                assert isinstance(input1, StageItemInputFinal)
                assert isinstance(input2, StageItemInputFinal)
                match_scores = scores.get(frozenset((input1.team_id, input2.team_id)))
                if match_scores is None:
                    continue

                body = {
                    "round_id": round_.id,
                    "stage_item_input1_score": match_scores[input1.team_id],
                    "stage_item_input2_score": match_scores[input2.team_id],
                }
                assert (
                    await send_tournament_request(
                        HTTPMethod.PUT, f"matches/{match.id}", auth_context, json=body
                    )
                    == SUCCESS_RESPONSE
                )

        input_ids = {
            input_.team_id: input_.id
            for input_ in (await get_stage_item(tournament_id, stage_item.id)).inputs
        }
        standings = await send_request(HTTPMethod.GET, f"tournaments/{tournament_id}/standings")
        player_response = await send_tournament_request(
            HTTPMethod.GET, "players?sort_by=elo_score&sort_direction=desc", auth_context
        )

    # Teams 1 and 2 both have a point, and team 2 has the better score difference. The unplayed
    # match doesn't count as a draw.
    assert standings["data"][str(stage_item.id)] == [
        {
            "stage_item_input_id": input_ids[teams[1].id],
            "wins": 1,
            "draws": 0,
            "losses": 1,
            "points": "1.00",
            "score_for": 4,
            "score_against": 2,
        },
        {
            "stage_item_input_id": input_ids[teams[0].id],
            "wins": 1,
            "draws": 0,
            "losses": 0,
            "points": "1.00",
            "score_for": 2,
            "score_against": 1,
        },
        {
            "stage_item_input_id": input_ids[teams[2].id],
            "wins": 0,
            "draws": 0,
            "losses": 1,
            "points": "0.00",
            "score_for": 0,
            "score_against": 3,
        },
    ]

    statistics = {
        player["id"]: (player["wins"], player["draws"], player["losses"], player["elo_score"])
        for player in player_response["data"]["players"]
    }
    assert [player["id"] for player in player_response["data"]["players"]] == [
        players[0].id,
        players[1].id,
        players[2].id,
    ]
    assert statistics[players[0].id][:3] == (1, 0, 0)
    assert statistics[players[1].id][:3] == (1, 0, 1)
    assert statistics[players[2].id][:3] == (0, 0, 1)
    assert int(statistics[players[0].id][3]) > 1200 > int(statistics[players[2].id][3])
