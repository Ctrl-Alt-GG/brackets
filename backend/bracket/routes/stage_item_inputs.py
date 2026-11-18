from typing import Annotated

from fastapi import APIRouter, Depends

from bracket.config import config
from bracket.database import DbSession
from bracket.logic.stage_items import update_stage_item_input as update_slot
from bracket.models.db.stage_item_inputs import StageItemInputUpdateBody
from bracket.models.db.stage_tree import StageItemWithRounds
from bracket.models.db.tournament import Tournament
from bracket.models.db.user import UserPublic
from bracket.routes.access import user_authenticated_for_tournament
from bracket.routes.models import SuccessResponse
from bracket.routes.resources import disallow_archived_tournament, stage_item_dependency
from bracket.utils.id_types import StageItemInputId, TournamentId

router = APIRouter(prefix=config.api_prefix)


@router.put(
    "/tournaments/{tournament_id}/stage_items/{stage_item_id}/inputs/{stage_item_input_id}",
    response_model=SuccessResponse,
)
async def update_stage_item_input(
    session: DbSession,
    tournament_id: TournamentId,
    stage_item_input_id: StageItemInputId,
    stage_item_body: StageItemInputUpdateBody,
    _: Annotated[UserPublic, Depends(user_authenticated_for_tournament)],
    stage_item: Annotated[StageItemWithRounds, Depends(stage_item_dependency)],
    ___: Annotated[Tournament, Depends(disallow_archived_tournament)],
) -> SuccessResponse:
    await update_slot(session, tournament_id, stage_item, stage_item_input_id, stage_item_body)
    return SuccessResponse()
