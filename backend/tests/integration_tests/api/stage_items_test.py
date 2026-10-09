from http import HTTPMethod

import pytest
from sqlalchemy.ext.asyncio import AsyncConnection

from bracket.models.db.stage_item import StageType
from bracket.models.db.stage_item_inputs import StageItemInputCreateBodyFinal
from bracket.models.db.tournament import TournamentStatus
from bracket.schema import matches, rounds, stage_items, stages
from bracket.sql.stage_items import get_stage_item
from bracket.utils.dummy_records import (
    DUMMY_RANKING1,
    DUMMY_STAGE1,
    DUMMY_STAGE2,
    DUMMY_STAGE_ITEM1,
    DUMMY_TEAM1,
    DUMMY_TOURNAMENT,
)
from tests.integration_tests.api.shared import (
    SUCCESS_RESPONSE,
    send_tournament_request,
)
from tests.integration_tests.models import AuthContext
from tests.integration_tests.sql import (
    assert_row_count_and_clear,
    inserted_ranking,
    inserted_stage,
    inserted_stage_item,
    inserted_team,
    inserted_tournament,
)


@pytest.mark.asyncio(loop_scope="session")
async def test_create_stage_item(
    startup_and_shutdown_uvicorn_server: None, auth_context: AuthContext
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
    ):
        assert team_inserted_1.id and team_inserted_2.id
        inputs = [
            StageItemInputCreateBodyFinal(slot=1, team_id=team_inserted_1.id).model_dump(),
            StageItemInputCreateBodyFinal(slot=2, team_id=team_inserted_2.id).model_dump(),
        ]
        assert (
            await send_tournament_request(
                HTTPMethod.POST,
                "stage_items",
                auth_context,
                json={
                    "type": StageType.SINGLE_ELIMINATION.value,
                    "team_count": 2,
                    "stage_id": stage_inserted_1.id,
                    "inputs": inputs,
                },
            )
            == SUCCESS_RESPONSE
        )
        await assert_row_count_and_clear(matches, 1)
        await assert_row_count_and_clear(rounds, 1)
        await assert_row_count_and_clear(stage_items, 1)
        await assert_row_count_and_clear(stages, 1)


@pytest.mark.asyncio(loop_scope="session")
async def test_delete_stage_item(
    startup_and_shutdown_uvicorn_server: None, auth_context: AuthContext
) -> None:
    async with (
        inserted_team(DUMMY_TEAM1.model_copy(update={"tournament_id": auth_context.tournament.id})),
        inserted_stage(
            DUMMY_STAGE2.model_copy(update={"tournament_id": auth_context.tournament.id})
        ) as stage_inserted_1,
        inserted_stage_item(
            DUMMY_STAGE_ITEM1.model_copy(
                update={"stage_id": stage_inserted_1.id, "ranking_id": auth_context.ranking.id}
            )
        ) as stage_item_inserted,
    ):
        assert (
            await send_tournament_request(
                HTTPMethod.DELETE, f"stage_items/{stage_item_inserted.id}", auth_context, {}
            )
            == SUCCESS_RESPONSE
        )
        await assert_row_count_and_clear(stage_items, 0)
        await assert_row_count_and_clear(stages, 1)


@pytest.mark.asyncio(loop_scope="session")
async def test_update_stage_item(
    conn: AsyncConnection, startup_and_shutdown_uvicorn_server: None, auth_context: AuthContext
) -> None:
    body = {"name": "Optimus", "ranking_id": auth_context.ranking.id}
    async with (
        inserted_stage(
            DUMMY_STAGE1.model_copy(update={"tournament_id": auth_context.tournament.id})
        ) as stage_inserted,
        inserted_stage_item(
            DUMMY_STAGE_ITEM1.model_copy(
                update={"stage_id": stage_inserted.id, "ranking_id": auth_context.ranking.id}
            )
        ) as stage_item_inserted,
    ):
        assert (
            await send_tournament_request(
                HTTPMethod.PUT, f"stage_items/{stage_item_inserted.id}", auth_context, json=body
            )
            == SUCCESS_RESPONSE
        )

        assert auth_context.tournament.id
        updated_stage_item = await get_stage_item(
            conn, auth_context.tournament.id, stage_item_inserted.id
        )
        assert updated_stage_item.name == body["name"]


@pytest.mark.asyncio(loop_scope="session")
async def test_stage_items_of_archived_tournament_are_read_only(
    startup_and_shutdown_uvicorn_server: None, auth_context: AuthContext
) -> None:
    async with (
        inserted_tournament(
            DUMMY_TOURNAMENT.model_copy(
                update={
                    "club_id": auth_context.club.id,
                    "dashboard_endpoint": None,
                    "status": TournamentStatus.ARCHIVED,
                }
            )
        ) as archived_tournament,
        inserted_ranking(
            DUMMY_RANKING1.model_copy(update={"tournament_id": archived_tournament.id})
        ) as ranking_inserted,
        inserted_stage(
            DUMMY_STAGE2.model_copy(update={"tournament_id": archived_tournament.id})
        ) as stage_inserted,
        inserted_stage_item(
            DUMMY_STAGE_ITEM1.model_copy(
                update={"stage_id": stage_inserted.id, "ranking_id": ranking_inserted.id}
            )
        ) as stage_item_inserted,
    ):
        archived_context = auth_context.model_copy(update={"tournament": archived_tournament})
        created = await send_tournament_request(
            HTTPMethod.POST,
            "stage_items",
            archived_context,
            json={
                "type": StageType.ROUND_ROBIN.value,
                "team_count": 2,
                "stage_id": stage_inserted.id,
            },
        )
        deleted = await send_tournament_request(
            HTTPMethod.DELETE, f"stage_items/{stage_item_inserted.id}", archived_context
        )
        await assert_row_count_and_clear(stage_items, 1)

    assert created == deleted == {"detail": "Can't update archived tournament"}


@pytest.mark.asyncio(loop_scope="session")
async def test_create_stage_item_with_ranking_of_other_tournament(
    startup_and_shutdown_uvicorn_server: None, auth_context: AuthContext
) -> None:
    """
    Regression test: a stage item could use another tournament's ranking, and was then deleted
    along with it.
    """
    async with (
        inserted_tournament(
            DUMMY_TOURNAMENT.model_copy(
                update={"club_id": auth_context.club.id, "dashboard_endpoint": None}
            )
        ) as other_tournament,
        inserted_ranking(
            DUMMY_RANKING1.model_copy(update={"tournament_id": other_tournament.id})
        ) as other_ranking,
        inserted_stage(
            DUMMY_STAGE2.model_copy(update={"tournament_id": auth_context.tournament.id})
        ) as stage_inserted,
    ):
        response = await send_tournament_request(
            HTTPMethod.POST,
            "stage_items",
            auth_context,
            json={
                "type": StageType.ROUND_ROBIN.value,
                "team_count": 2,
                "stage_id": stage_inserted.id,
                "ranking_id": other_ranking.id,
            },
        )
        await assert_row_count_and_clear(stage_items, 0)

    assert response == {"detail": f"Could not find Ranking(s) with ID {other_ranking.id}"}
