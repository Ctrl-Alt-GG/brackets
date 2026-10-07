from http import HTTPMethod

import pytest
from heliclockter import timedelta
from sqlalchemy.ext.asyncio import AsyncConnection

from bracket.logic.scheduling.builder import build_matches_for_stage_item
from bracket.models.db.stage_item import StageItemWithInputsCreate, StageType
from bracket.models.db.stage_item_inputs import (
    StageItemInputCreateBodyFinal,
    StageItemInputCreateBodyTentative,
)
from bracket.sql.shared import sql_delete_stage_item_with_foreign_keys
from bracket.sql.stage_items import sql_create_stage_item_with_inputs
from bracket.sql.stages import get_full_tournament_details
from bracket.sql.tournaments import sql_get_tournament
from bracket.utils.dummy_records import (
    DUMMY_STAGE2,
    DUMMY_STAGE_ITEM1,
    DUMMY_STAGE_ITEM3,
    DUMMY_TEAM1,
)
from tests.integration_tests.api.shared import (
    SUCCESS_RESPONSE,
    send_tournament_request,
)
from tests.integration_tests.models import AuthContext
from tests.integration_tests.sql import (
    inserted_stage,
    inserted_team,
)


@pytest.mark.asyncio(loop_scope="session")
async def test_schedule_all_matches(
    conn: AsyncConnection, startup_and_shutdown_uvicorn_server: None, auth_context: AuthContext
) -> None:
    async with (
        inserted_stage(
            DUMMY_STAGE2.model_copy(update={"tournament_id": auth_context.tournament.id})
        ) as stage_inserted_1,
        inserted_team(
            DUMMY_TEAM1.model_copy(update={"tournament_id": auth_context.tournament.id})
        ) as team_inserted_1,
        inserted_team(
            DUMMY_TEAM1.model_copy(update={"tournament_id": auth_context.tournament.id})
        ) as team_inserted_2,
        inserted_team(
            DUMMY_TEAM1.model_copy(update={"tournament_id": auth_context.tournament.id})
        ) as team_inserted_3,
        inserted_team(
            DUMMY_TEAM1.model_copy(update={"tournament_id": auth_context.tournament.id})
        ) as team_inserted_4,
    ):
        tournament_id = auth_context.tournament.id
        stage_item_1 = await sql_create_stage_item_with_inputs(
            conn,
            tournament_id,
            StageItemWithInputsCreate(
                stage_id=stage_inserted_1.id,
                name=DUMMY_STAGE_ITEM1.name,
                team_count=DUMMY_STAGE_ITEM1.team_count,
                type=DUMMY_STAGE_ITEM1.type,
                inputs=[
                    StageItemInputCreateBodyFinal(
                        slot=1,
                        team_id=team_inserted_1.id,
                    ),
                    StageItemInputCreateBodyFinal(
                        slot=2,
                        team_id=team_inserted_2.id,
                    ),
                    StageItemInputCreateBodyFinal(
                        slot=3,
                        team_id=team_inserted_3.id,
                    ),
                    StageItemInputCreateBodyFinal(
                        slot=4,
                        team_id=team_inserted_4.id,
                    ),
                ],
            ),
        )
        stage_item_2 = await sql_create_stage_item_with_inputs(
            conn,
            tournament_id,
            StageItemWithInputsCreate(
                stage_id=stage_inserted_1.id,
                name=DUMMY_STAGE_ITEM3.name,
                team_count=2,
                type=DUMMY_STAGE_ITEM3.type,
                inputs=[
                    StageItemInputCreateBodyTentative(
                        slot=1,
                        winner_from_stage_item_id=stage_item_1.id,
                        winner_position=1,
                    ),
                    StageItemInputCreateBodyTentative(
                        slot=2,
                        winner_from_stage_item_id=stage_item_1.id,
                        winner_position=2,
                    ),
                ],
            ),
        )
        await build_matches_for_stage_item(conn, stage_item_1, tournament_id)
        await build_matches_for_stage_item(conn, stage_item_2, tournament_id)

        response = await send_tournament_request(
            HTTPMethod.POST,
            "schedule_matches",
            auth_context,
        )
        stages = await get_full_tournament_details(conn, tournament_id)
        tournament = await sql_get_tournament(conn, tournament_id)

        await sql_delete_stage_item_with_foreign_keys(conn, stage_item_2.id)
        await sql_delete_stage_item_with_foreign_keys(conn, stage_item_1.id)

    assert response == SUCCESS_RESPONSE

    round_length = timedelta(minutes=tournament.duration_minutes + tournament.margin_minutes)
    stage_items = {stage_item.id: stage_item for stage_item in stages[0].stage_items}

    round_robin_rounds = sorted(stage_items[stage_item_1.id].rounds, key=lambda round_: round_.id)
    assert len(round_robin_rounds) == 3
    for index, round_ in enumerate(round_robin_rounds):
        assert len(round_.matches) == 2
        assert {match.start_time for match in round_.matches} == {
            tournament.start_time + index * round_length
        }

    # Stage items of the same stage are played in parallel.
    [elimination_round] = stage_items[stage_item_2.id].rounds
    assert [match.start_time for match in elimination_round.matches] == [tournament.start_time]


@pytest.mark.asyncio(loop_scope="session")
async def test_schedule_matches_with_custom_stage_duration(
    conn: AsyncConnection, startup_and_shutdown_uvicorn_server: None, auth_context: AuthContext
) -> None:
    tournament_id = auth_context.tournament.id

    async with inserted_stage(
        DUMMY_STAGE2.model_copy(
            update={"tournament_id": tournament_id, "custom_duration_minutes": 30}
        )
    ) as stage_inserted:
        create_response = await send_tournament_request(
            HTTPMethod.POST,
            "stage_items",
            auth_context,
            json={
                "type": StageType.ROUND_ROBIN.value,
                "team_count": 4,
                "stage_id": stage_inserted.id,
            },
        )
        [created_stage] = await get_full_tournament_details(conn, tournament_id)

        update_response = await send_tournament_request(
            HTTPMethod.PUT,
            f"stages/{stage_inserted.id}",
            auth_context,
            json={"name": stage_inserted.name, "custom_duration_minutes": 45},
        )
        [updated_stage] = await get_full_tournament_details(conn, tournament_id)
        tournament = await sql_get_tournament(conn, tournament_id)

        [stage_item] = updated_stage.stage_items
        await sql_delete_stage_item_with_foreign_keys(conn, stage_item.id)

    assert create_response == SUCCESS_RESPONSE
    assert update_response == SUCCESS_RESPONSE

    # New matches last as long as their stage says, and changing that reschedules them.
    for stage, duration_minutes in ((created_stage, 30), (updated_stage, 45)):
        round_length = timedelta(minutes=duration_minutes + tournament.margin_minutes)
        [stage_item] = stage.stage_items
        assert {
            (match.start_time, match.duration_minutes)
            for round_ in stage_item.rounds
            for match in round_.matches
        } == {
            (tournament.start_time + index * round_length, duration_minutes) for index in range(3)
        }
