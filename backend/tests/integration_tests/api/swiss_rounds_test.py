from contextlib import AsyncExitStack
from http import HTTPMethod

import pytest
from sqlalchemy.ext.asyncio import AsyncConnection

from bracket.models.db.stage_item import StageItemWithInputsCreate, StageType
from bracket.models.db.stage_item_inputs import (
    StageItemInputCreateBodyEmpty,
    StageItemInputCreateBodyFinal,
)
from bracket.models.db.util import RoundWithMatches
from bracket.sql.shared import sql_delete_stage_item_with_foreign_keys
from bracket.sql.stage_items import get_stage_item, sql_create_stage_item_with_inputs
from bracket.utils.dummy_records import DUMMY_STAGE1, DUMMY_TEAM1
from bracket.utils.id_types import StageItemInputId
from tests.integration_tests.api.shared import SUCCESS_RESPONSE, send_tournament_request
from tests.integration_tests.models import AuthContext
from tests.integration_tests.sql import inserted_stage, inserted_team


def get_pairs(round_: RoundWithMatches) -> set[frozenset[StageItemInputId | None]]:
    return {
        frozenset((match.stage_item_input1_id, match.stage_item_input2_id))
        for match in round_.matches
    }


@pytest.mark.asyncio(loop_scope="session")
async def test_generate_and_publish_swiss_rounds(
    conn: AsyncConnection, startup_and_shutdown_uvicorn_server: None, auth_context: AuthContext
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
            for index in range(5)
        ]
        stage_item = await sql_create_stage_item_with_inputs(
            conn,
            tournament_id,
            StageItemWithInputsCreate(
                stage_id=stage.id,
                name="Swiss",
                team_count=len(teams),
                type=StageType.SWISS,
                inputs=[
                    StageItemInputCreateBodyFinal(slot=index + 1, team_id=team.id)
                    for index, team in enumerate(teams)
                ],
            ),
        )
        stack.push_async_callback(sql_delete_stage_item_with_foreign_keys, conn, stage_item.id)
        round_body = {"stage_item_id": stage_item.id}

        response = await send_tournament_request(
            HTTPMethod.POST, "rounds", auth_context, json=round_body
        )
        assert response == SUCCESS_RESPONSE

        generated = await get_stage_item(conn, tournament_id, stage_item.id)
        [first_round] = generated.rounds
        assert first_round.is_draft
        assert len(first_round.matches) == 2
        first_round_players = {input_id for pair in get_pairs(first_round) for input_id in pair}
        [sat_out] = {input_.id for input_ in generated.inputs} - first_round_players

        response = await send_tournament_request(
            HTTPMethod.POST, "rounds", auth_context, json=round_body
        )
        assert response == {"detail": f"Publish or discard the draft {first_round.name} first"}

        response = await send_tournament_request(
            HTTPMethod.PUT,
            f"rounds/{first_round.id}",
            auth_context,
            json={"name": first_round.name, "is_draft": False},
        )
        assert response == SUCCESS_RESPONSE

        response = await send_tournament_request(
            HTTPMethod.POST, "rounds", auth_context, json=round_body
        )
        assert response == SUCCESS_RESPONSE

        rounds = sorted(
            (await get_stage_item(conn, tournament_id, stage_item.id)).rounds,
            key=lambda round_: round_.id,
        )
        assert [round_.is_draft for round_ in rounds] == [False, True]
        second_round = rounds[1]
        assert len(second_round.matches) == 2
        assert not get_pairs(first_round) & get_pairs(second_round)
        assert sat_out in {input_id for pair in get_pairs(second_round) for input_id in pair}

        # Every match of a round starts together, after the previous round.
        [first_start] = {match.start_time for match in rounds[0].matches}
        [second_start] = {match.start_time for match in second_round.matches}
        assert first_start is not None
        assert second_start is not None
        assert second_start > first_start


@pytest.mark.asyncio(loop_scope="session")
async def test_generate_round_needs_swiss_stage_item_with_teams(
    conn: AsyncConnection, startup_and_shutdown_uvicorn_server: None, auth_context: AuthContext
) -> None:
    tournament_id = auth_context.tournament.id
    async with (
        inserted_stage(DUMMY_STAGE1.model_copy(update={"tournament_id": tournament_id})) as stage,
        inserted_team(DUMMY_TEAM1.model_copy(update={"tournament_id": tournament_id})) as team,
    ):
        round_robin = await sql_create_stage_item_with_inputs(
            conn,
            tournament_id,
            StageItemWithInputsCreate(
                stage_id=stage.id,
                name="Group",
                team_count=2,
                type=StageType.ROUND_ROBIN,
                inputs=[
                    StageItemInputCreateBodyFinal(slot=1, team_id=team.id),
                    StageItemInputCreateBodyEmpty(slot=2),
                ],
            ),
        )
        swiss = await sql_create_stage_item_with_inputs(
            conn,
            tournament_id,
            StageItemWithInputsCreate(
                stage_id=stage.id,
                name="Swiss",
                team_count=2,
                type=StageType.SWISS,
                inputs=[
                    StageItemInputCreateBodyFinal(slot=1, team_id=team.id),
                    StageItemInputCreateBodyEmpty(slot=2),
                ],
            ),
        )
        try:
            assert await send_tournament_request(
                HTTPMethod.POST, "rounds", auth_context, json={"stage_item_id": round_robin.id}
            ) == {"detail": "Rounds of round robin stage items are created automatically"}
            assert await send_tournament_request(
                HTTPMethod.POST, "rounds", auth_context, json={"stage_item_id": swiss.id}
            ) == {"detail": "Assign at least two active teams to this stage item first"}
        finally:
            await sql_delete_stage_item_with_foreign_keys(conn, swiss.id)
            await sql_delete_stage_item_with_foreign_keys(conn, round_robin.id)
