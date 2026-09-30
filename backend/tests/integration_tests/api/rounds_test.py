import pytest

from bracket.database import database
from bracket.models.db.round import Round
from bracket.models.db.stage_item import StageType
from bracket.models.db.stage_item_inputs import StageItemInputInsertable
from bracket.schema import rounds
from bracket.sql.stage_items import get_stage_item
from bracket.utils.db import fetch_one_parsed_certain
from bracket.utils.dummy_records import (
    DUMMY_ROUND1,
    DUMMY_STAGE1,
    DUMMY_STAGE_ITEM1,
    DUMMY_TEAM1,
    DUMMY_TEAM2,
)
from bracket.utils.http import HTTPMethod
from tests.integration_tests.api.shared import SUCCESS_RESPONSE, send_tournament_request
from tests.integration_tests.models import AuthContext
from tests.integration_tests.sql import (
    assert_row_count_and_clear,
    inserted_round,
    inserted_stage,
    inserted_stage_item,
    inserted_stage_item_input,
    inserted_team,
)


@pytest.mark.asyncio(loop_scope="session")
async def test_create_round(
    startup_and_shutdown_uvicorn_server: None, auth_context: AuthContext
) -> None:
    async with (
        inserted_team(
            DUMMY_TEAM1.model_copy(update={"tournament_id": auth_context.tournament.id})
        ) as team1_inserted,
        inserted_team(
            DUMMY_TEAM2.model_copy(update={"tournament_id": auth_context.tournament.id})
        ) as team2_inserted,
        inserted_stage(
            DUMMY_STAGE1.model_copy(update={"tournament_id": auth_context.tournament.id})
        ) as stage_inserted,
        inserted_stage_item(
            DUMMY_STAGE_ITEM1.model_copy(
                update={
                    "stage_id": stage_inserted.id,
                    "type": StageType.SWISS,
                    "ranking_id": auth_context.ranking.id,
                }
            )
        ) as stage_item_inserted,
        inserted_stage_item_input(
            StageItemInputInsertable(
                slot=1,
                team_id=team1_inserted.id,
                tournament_id=auth_context.tournament.id,
                stage_item_id=stage_item_inserted.id,
            )
        ),
        inserted_stage_item_input(
            StageItemInputInsertable(
                slot=2,
                team_id=team2_inserted.id,
                tournament_id=auth_context.tournament.id,
                stage_item_id=stage_item_inserted.id,
            )
        ),
    ):
        assert (
            await send_tournament_request(
                HTTPMethod.POST,
                "rounds",
                auth_context,
                json={"stage_item_id": stage_item_inserted.id},
            )
            == SUCCESS_RESPONSE
        )
        stage_item = await get_stage_item(auth_context.tournament.id, stage_item_inserted.id)
        [round_] = stage_item.rounds
        assert round_.is_draft
        assert len(round_.matches) == 1

        await assert_row_count_and_clear(rounds, 1)


@pytest.mark.asyncio(loop_scope="session")
async def test_delete_round(
    startup_and_shutdown_uvicorn_server: None, auth_context: AuthContext
) -> None:
    async with (
        inserted_team(DUMMY_TEAM1.model_copy(update={"tournament_id": auth_context.tournament.id})),
        inserted_stage(
            DUMMY_STAGE1.model_copy(update={"tournament_id": auth_context.tournament.id})
        ) as stage_inserted,
        inserted_stage_item(
            DUMMY_STAGE_ITEM1.model_copy(
                update={"stage_id": stage_inserted.id, "ranking_id": auth_context.ranking.id}
            )
        ) as stage_item_inserted,
        inserted_round(
            DUMMY_ROUND1.model_copy(update={"stage_item_id": stage_item_inserted.id})
        ) as round_inserted,
    ):
        assert (
            await send_tournament_request(
                HTTPMethod.DELETE, f"rounds/{round_inserted.id}", auth_context, {}
            )
            == SUCCESS_RESPONSE
        )
        await assert_row_count_and_clear(rounds, 0)


@pytest.mark.asyncio(loop_scope="session")
async def test_update_round(
    startup_and_shutdown_uvicorn_server: None, auth_context: AuthContext
) -> None:
    body = {"name": "Some new name", "is_draft": True}
    async with (
        inserted_team(DUMMY_TEAM1.model_copy(update={"tournament_id": auth_context.tournament.id})),
        inserted_stage(
            DUMMY_STAGE1.model_copy(update={"tournament_id": auth_context.tournament.id})
        ) as stage_inserted,
        inserted_stage_item(
            DUMMY_STAGE_ITEM1.model_copy(
                update={"stage_id": stage_inserted.id, "ranking_id": auth_context.ranking.id}
            )
        ) as stage_item_inserted,
        inserted_round(
            DUMMY_ROUND1.model_copy(update={"stage_item_id": stage_item_inserted.id})
        ) as round_inserted,
    ):
        assert (
            await send_tournament_request(
                HTTPMethod.PUT, f"rounds/{round_inserted.id}", auth_context, None, body
            )
            == SUCCESS_RESPONSE
        )
        updated_round = await fetch_one_parsed_certain(
            database, Round, query=rounds.select().where(rounds.c.id == round_inserted.id)
        )
        assert updated_round.name == body["name"]
        assert updated_round.is_draft == body["is_draft"]

        await assert_row_count_and_clear(rounds, 1)
