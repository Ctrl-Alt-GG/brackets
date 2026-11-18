from typing import Annotated

from fastapi import APIRouter, Depends

from bracket.config import config
from bracket.database import DbSession
from bracket.logic import stage_items as stage_item_logic
from bracket.models.db.stage_item import StageItemCreateBody, StageItemUpdateBody
from bracket.models.db.stage_tree import StageItemWithRounds
from bracket.models.db.tournament import Tournament
from bracket.models.db.user import UserPublic
from bracket.routes.access import user_authenticated_for_tournament
from bracket.routes.models import SuccessResponse
from bracket.routes.resources import disallow_archived_tournament, stage_item_dependency
from bracket.utils.id_types import StageItemId, TournamentId

router = APIRouter(prefix=config.api_prefix)

TournamentOrganizer = Annotated[UserPublic, Depends(user_authenticated_for_tournament)]
OpenTournament = Annotated[Tournament, Depends(disallow_archived_tournament)]
LoadedStageItem = Annotated[StageItemWithRounds, Depends(stage_item_dependency)]


@router.delete(
    "/tournaments/{tournament_id}/stage_items/{stage_item_id}", response_model=SuccessResponse
)
async def delete_stage_item(
    session: DbSession,
    tournament_id: TournamentId,
    stage_item_id: StageItemId,
    _: TournamentOrganizer,
    __: LoadedStageItem,
    ___: OpenTournament,
) -> SuccessResponse:
    """
    Delete a stage item with its rounds and matches.

    Slots of later stage items that take a team from it become open again. That is refused
    once such a stage item has results, which belong to the teams that advanced.
    """
    await stage_item_logic.delete_stage_item(session, tournament_id, stage_item_id)
    return SuccessResponse()


@router.post("/tournaments/{tournament_id}/stage_items", response_model=SuccessResponse)
async def create_stage_item(
    session: DbSession,
    tournament_id: TournamentId,
    stage_body: StageItemCreateBody,
    user: TournamentOrganizer,
    _: OpenTournament,
) -> SuccessResponse:
    await stage_item_logic.create_stage_item(session, tournament_id, stage_body, user)
    return SuccessResponse()


@router.put(
    "/tournaments/{tournament_id}/stage_items/{stage_item_id}", response_model=SuccessResponse
)
async def update_stage_item(
    session: DbSession,
    tournament_id: TournamentId,
    stage_item_body: StageItemUpdateBody,
    _: TournamentOrganizer,
    __: OpenTournament,
    stage_item: LoadedStageItem,
) -> SuccessResponse:
    await stage_item_logic.rename_stage_item(
        session, tournament_id, stage_item, stage_item_body.name
    )
    return SuccessResponse()
