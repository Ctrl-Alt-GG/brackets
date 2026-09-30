from fastapi import APIRouter, Depends

from bracket.config import config
from bracket.logic.planning.matches import schedule_all_matches
from bracket.logic.ranking.calculation import recalculate_ranking_for_stage_item
from bracket.logic.ranking.elimination import (
    update_inputs_in_complete_elimination_stage_item,
)
from bracket.logic.scheduling.builder import (
    build_matches_for_stage_item,
)
from bracket.logic.subscriptions import check_requirement
from bracket.models.db.stage_item import (
    StageItemCreateBody,
    StageItemUpdateBody,
    StageType,
)
from bracket.models.db.tournament import Tournament
from bracket.models.db.user import UserPublic
from bracket.models.db.util import StageItemWithRounds
from bracket.routes.auth import (
    user_authenticated_for_tournament,
)
from bracket.routes.models import SuccessResponse
from bracket.routes.util import disallow_archived_tournament, stage_item_dependency
from bracket.sql.shared import sql_delete_stage_item_with_foreign_keys
from bracket.sql.stage_items import (
    sql_create_stage_item_with_empty_inputs,
    sql_update_stage_item_name,
)
from bracket.sql.stages import get_full_tournament_details
from bracket.sql.validation import check_foreign_keys_belong_to_tournament
from bracket.utils.errors import (
    ForeignKey,
    check_foreign_key_violation,
)
from bracket.utils.id_types import StageItemId, TournamentId

router = APIRouter(prefix=config.api_prefix)


@router.delete(
    "/tournaments/{tournament_id}/stage_items/{stage_item_id}", response_model=SuccessResponse
)
async def delete_stage_item(
    tournament_id: TournamentId,
    stage_item_id: StageItemId,
    _: UserPublic = Depends(user_authenticated_for_tournament),
    __: StageItemWithRounds = Depends(stage_item_dependency),
) -> SuccessResponse:
    with check_foreign_key_violation(
        {ForeignKey.matches_stage_item_input1_id_fkey, ForeignKey.matches_stage_item_input2_id_fkey}
    ):
        await sql_delete_stage_item_with_foreign_keys(stage_item_id)
    await schedule_all_matches(tournament_id)
    return SuccessResponse()


@router.post("/tournaments/{tournament_id}/stage_items", response_model=SuccessResponse)
async def create_stage_item(
    tournament_id: TournamentId,
    stage_body: StageItemCreateBody,
    user: UserPublic = Depends(user_authenticated_for_tournament),
) -> SuccessResponse:
    await check_foreign_keys_belong_to_tournament(stage_body, tournament_id)

    stages = await get_full_tournament_details(tournament_id)
    existing_stage_items = [stage_item for stage in stages for stage_item in stage.stage_items]
    check_requirement(existing_stage_items, user, "max_stage_items")

    stage_item = await sql_create_stage_item_with_empty_inputs(tournament_id, stage_body)
    await build_matches_for_stage_item(stage_item, tournament_id)
    await schedule_all_matches(tournament_id)
    return SuccessResponse()


@router.put(
    "/tournaments/{tournament_id}/stage_items/{stage_item_id}", response_model=SuccessResponse
)
async def update_stage_item(
    tournament_id: TournamentId,
    stage_item_id: StageItemId,
    stage_item_body: StageItemUpdateBody,
    _: UserPublic = Depends(user_authenticated_for_tournament),
    __: Tournament = Depends(disallow_archived_tournament),
    stage_item: StageItemWithRounds = Depends(stage_item_dependency),
) -> SuccessResponse:
    await sql_update_stage_item_name(stage_item.id, stage_item_body.name)
    await recalculate_ranking_for_stage_item(tournament_id, stage_item)
    if stage_item.type == StageType.SINGLE_ELIMINATION:
        await update_inputs_in_complete_elimination_stage_item(stage_item)
    return SuccessResponse()
