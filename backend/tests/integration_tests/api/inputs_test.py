from http import HTTPMethod

import pytest

from bracket.models.db.stage_item_inputs import StageItemInputInsertable
from bracket.utils.dummy_records import (
    DUMMY_RANKING1,
    DUMMY_STAGE1,
    DUMMY_STAGE2,
    DUMMY_STAGE_ITEM1,
    DUMMY_TEAM1,
    DUMMY_TOURNAMENT,
)
from tests.integration_tests.api.shared import (
    send_tournament_request,
)
from tests.integration_tests.models import AuthContext
from tests.integration_tests.sql import (
    inserted_ranking,
    inserted_stage,
    inserted_stage_item,
    inserted_stage_item_input,
    inserted_team,
    inserted_tournament,
)


@pytest.mark.asyncio(loop_scope="session")
async def test_available_inputs(
    startup_and_shutdown_uvicorn_server: None, auth_context: AuthContext
) -> None:
    async with (
        inserted_team(
            DUMMY_TEAM1.model_copy(update={"tournament_id": auth_context.tournament.id})
        ) as team_inserted,
        inserted_stage(
            DUMMY_STAGE1.model_copy(update={"tournament_id": auth_context.tournament.id})
        ) as stage_inserted_1,
        inserted_stage_item(
            DUMMY_STAGE_ITEM1.model_copy(
                update={"stage_id": stage_inserted_1.id, "ranking_id": auth_context.ranking.id}
            )
        ),
    ):
        response = await send_tournament_request(HTTPMethod.GET, "available_inputs", auth_context)

    assert response == {
        "data": {str(stage_inserted_1.id): [{"team_id": team_inserted.id, "already_taken": False}]}
    }


@pytest.mark.asyncio(loop_scope="session")
async def test_update_stage_item_input(
    startup_and_shutdown_uvicorn_server: None, auth_context: AuthContext
) -> None:
    async with (
        inserted_team(
            DUMMY_TEAM1.model_copy(update={"tournament_id": auth_context.tournament.id})
        ) as team_inserted,
        inserted_stage(
            DUMMY_STAGE1.model_copy(update={"tournament_id": auth_context.tournament.id})
        ) as stage_inserted_1,
        inserted_stage_item(
            DUMMY_STAGE_ITEM1.model_copy(
                update={"stage_id": stage_inserted_1.id, "ranking_id": auth_context.ranking.id}
            )
        ) as stage_item_inserted,
        inserted_stage_item_input(
            StageItemInputInsertable(
                slot=0,
                team_id=None,
                tournament_id=auth_context.tournament.id,
                stage_item_id=stage_item_inserted.id,
            )
        ) as stage_item_input1_inserted,
    ):
        response = await send_tournament_request(
            HTTPMethod.PUT,
            f"stage_items/{stage_item_inserted.id}/inputs/{stage_item_input1_inserted.id}",
            auth_context,
            json={"team_id": team_inserted.id},
        )

    assert response == {"success": True}


@pytest.mark.asyncio(loop_scope="session")
async def test_update_stage_item_input_invalid_team(
    startup_and_shutdown_uvicorn_server: None, auth_context: AuthContext
) -> None:
    async with (
        inserted_stage(
            DUMMY_STAGE1.model_copy(update={"tournament_id": auth_context.tournament.id})
        ) as stage_inserted_1,
        inserted_stage_item(
            DUMMY_STAGE_ITEM1.model_copy(
                update={"stage_id": stage_inserted_1.id, "ranking_id": auth_context.ranking.id}
            )
        ) as stage_item_inserted,
        inserted_stage_item_input(
            StageItemInputInsertable(
                slot=0,
                team_id=None,
                tournament_id=auth_context.tournament.id,
                stage_item_id=stage_item_inserted.id,
            )
        ) as stage_item_input1_inserted,
    ):
        response = await send_tournament_request(
            HTTPMethod.PUT,
            f"stage_items/{stage_item_inserted.id}/inputs/{stage_item_input1_inserted.id}",
            auth_context,
            json={"team_id": -42},
        )

    assert response == {"detail": "Could not find team with id -42"}


@pytest.mark.asyncio(loop_scope="session")
async def test_update_stage_item_input_from_other_tournament(
    startup_and_shutdown_uvicorn_server: None, auth_context: AuthContext
) -> None:
    """Regression test: an input could take its teams from another tournament's stage item."""
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
            DUMMY_STAGE1.model_copy(update={"tournament_id": other_tournament.id})
        ) as other_stage,
        inserted_stage_item(
            DUMMY_STAGE_ITEM1.model_copy(
                update={"stage_id": other_stage.id, "ranking_id": other_ranking.id}
            )
        ) as other_stage_item,
        inserted_stage(
            DUMMY_STAGE2.model_copy(update={"tournament_id": auth_context.tournament.id})
        ) as stage_inserted,
        inserted_stage_item(
            DUMMY_STAGE_ITEM1.model_copy(
                update={"stage_id": stage_inserted.id, "ranking_id": auth_context.ranking.id}
            )
        ) as stage_item_inserted,
        inserted_stage_item_input(
            StageItemInputInsertable(
                slot=0,
                team_id=None,
                tournament_id=auth_context.tournament.id,
                stage_item_id=stage_item_inserted.id,
            )
        ) as stage_item_input_inserted,
    ):
        response = await send_tournament_request(
            HTTPMethod.PUT,
            f"stage_items/{stage_item_inserted.id}/inputs/{stage_item_input_inserted.id}",
            auth_context,
            json={"winner_from_stage_item_id": other_stage_item.id, "winner_position": 1},
        )

    assert response == {"detail": f"Could not find stage item with id {other_stage_item.id}"}
