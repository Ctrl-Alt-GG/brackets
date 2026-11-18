from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException
from starlette import status

from bracket.config import config
from bracket.database import DbSession
from bracket.logic import stages as stage_logic
from bracket.models.db.stage import StageActivateBody, StageUpdateBody
from bracket.models.db.stage_tree import StageWithStageItems
from bracket.models.db.tournament import Tournament
from bracket.models.db.user import UserPublic
from bracket.routes.access import (
    user_authenticated_for_tournament,
    user_authenticated_or_rate_limited_visitor,
)
from bracket.routes.models import (
    StageItemInputOptionsResponse,
    StageRankingResponse,
    StagesWithStageItemsResponse,
    SuccessResponse,
)
from bracket.routes.resources import disallow_archived_tournament, stage_dependency
from bracket.utils.id_types import TournamentId

router = APIRouter(prefix=config.api_prefix)

TournamentOrganizer = Annotated[UserPublic, Depends(user_authenticated_for_tournament)]
OpenTournament = Annotated[Tournament, Depends(disallow_archived_tournament)]
LoadedStage = Annotated[StageWithStageItems, Depends(stage_dependency)]


@router.get("/tournaments/{tournament_id}/stages", response_model=StagesWithStageItemsResponse)
async def get_stages(
    session: DbSession,
    tournament_id: TournamentId,
    user: Annotated[UserPublic | None, Depends(user_authenticated_or_rate_limited_visitor)],
    no_draft_rounds: bool = False,
) -> StagesWithStageItemsResponse:
    if no_draft_rounds is False and user is None:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Can't view draft rounds when not authorized",
        )

    return StagesWithStageItemsResponse(
        data=await stage_logic.get_stages_with_team_totals(
            session, tournament_id, no_draft_rounds=no_draft_rounds
        )
    )


@router.delete("/tournaments/{tournament_id}/stages/{stage_id}", response_model=SuccessResponse)
async def delete_stage(
    session: DbSession,
    tournament_id: TournamentId,
    _: TournamentOrganizer,
    __: OpenTournament,
    stage: LoadedStage,
) -> SuccessResponse:
    await stage_logic.delete_stage(session, tournament_id, stage)
    return SuccessResponse()


@router.post("/tournaments/{tournament_id}/stages", response_model=SuccessResponse)
async def create_stage(
    session: DbSession,
    tournament_id: TournamentId,
    user: TournamentOrganizer,
    _: OpenTournament,
) -> SuccessResponse:
    await stage_logic.create_stage(session, tournament_id, user)
    return SuccessResponse()


@router.put("/tournaments/{tournament_id}/stages/{stage_id}", response_model=SuccessResponse)
async def update_stage(
    session: DbSession,
    tournament_id: TournamentId,
    stage_body: StageUpdateBody,
    _: TournamentOrganizer,
    __: OpenTournament,
    stage: LoadedStage,
) -> SuccessResponse:
    await stage_logic.update_stage(session, tournament_id, stage, stage_body)
    return SuccessResponse()


@router.post("/tournaments/{tournament_id}/stages/activate", response_model=SuccessResponse)
async def activate_next_stage(
    session: DbSession,
    tournament_id: TournamentId,
    stage_body: StageActivateBody,
    _: TournamentOrganizer,
    __: OpenTournament,
) -> SuccessResponse:
    await stage_logic.activate_adjacent_stage(
        session, tournament_id, stage_body.direction, discard_results=stage_body.discard_results
    )
    return SuccessResponse()


@router.get(
    "/tournaments/{tournament_id}/available_inputs",
    response_model=StageItemInputOptionsResponse,
)
async def get_available_inputs(
    session: DbSession, tournament_id: TournamentId, _: TournamentOrganizer
) -> StageItemInputOptionsResponse:
    return StageItemInputOptionsResponse(
        data=await stage_logic.get_available_inputs(session, tournament_id)
    )


@router.get("/tournaments/{tournament_id}/next_stage_rankings")
async def get_next_stage_rankings(
    session: DbSession, tournament_id: TournamentId, _: TournamentOrganizer
) -> StageRankingResponse:
    """
    Get the teams that take the slots of the next stage once it is activated.

    A slot that can't be decided yet is left out: its source ranks fewer teams than the position
    the slot takes. `tied_team` names a team that is level on every criterion with the one that
    gets the slot, which only seeding put behind it.
    """
    return StageRankingResponse(
        data=await stage_logic.get_advancement_preview(session, tournament_id)
    )
