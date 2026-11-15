from fastapi import APIRouter, Depends, HTTPException
from starlette import status

from bracket.config import config
from bracket.database import DbSession
from bracket.logic.planning.conflicts import handle_conflicts
from bracket.logic.planning.matches import schedule_all_matches
from bracket.logic.scheduling.builder import determine_available_inputs
from bracket.logic.scheduling.handle_stage_activation import (
    count_results_in_stage,
    get_adjacent_stage,
    get_updates_to_inputs_in_activated_stage,
    update_matches_in_activated_stage,
    update_matches_in_deactivated_stage,
)
from bracket.logic.subscriptions import check_requirement
from bracket.models.db.stage import Stage, StageActivateBody, StageUpdateBody
from bracket.models.db.tournament import Tournament
from bracket.models.db.user import UserPublic
from bracket.models.db.util import StageWithStageItems
from bracket.routes.auth import (
    user_authenticated_for_tournament,
    user_authenticated_or_rate_limited_visitor,
)
from bracket.routes.models import (
    StageItemInputOptionsResponse,
    StageRankingResponse,
    StagesWithStageItemsResponse,
    SuccessResponse,
)
from bracket.routes.util import disallow_archived_tournament, stage_dependency
from bracket.sql.stages import (
    get_full_tournament_details,
    sql_activate_next_stage,
    sql_create_stage,
    sql_delete_stage,
    sql_update_stage,
)
from bracket.sql.teams import get_teams_with_members
from bracket.utils.id_types import StageId, TournamentId

router = APIRouter(prefix=config.api_prefix)


@router.get("/tournaments/{tournament_id}/stages", response_model=StagesWithStageItemsResponse)
async def get_stages(
    session: DbSession,
    tournament_id: TournamentId,
    user: UserPublic | None = Depends(user_authenticated_or_rate_limited_visitor),
    no_draft_rounds: bool = False,
) -> StagesWithStageItemsResponse:
    if no_draft_rounds is False and user is None:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Can't view draft rounds when not authorized",
        )

    stages_ = await get_full_tournament_details(
        session, tournament_id, no_draft_rounds=no_draft_rounds, with_team_totals=True
    )
    return StagesWithStageItemsResponse(data=stages_)


@router.delete("/tournaments/{tournament_id}/stages/{stage_id}", response_model=SuccessResponse)
async def delete_stage(
    session: DbSession,
    tournament_id: TournamentId,
    stage_id: StageId,
    _: UserPublic = Depends(user_authenticated_for_tournament),
    __: Tournament = Depends(disallow_archived_tournament),
    stage: StageWithStageItems = Depends(stage_dependency),
) -> SuccessResponse:
    if len(stage.stage_items) > 0:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Stage contains stage items, please delete those first",
        )

    await sql_delete_stage(session, tournament_id, stage_id)

    return SuccessResponse()


@router.post("/tournaments/{tournament_id}/stages", response_model=SuccessResponse)
async def create_stage(
    session: DbSession,
    tournament_id: TournamentId,
    user: UserPublic = Depends(user_authenticated_for_tournament),
    _: Tournament = Depends(disallow_archived_tournament),
) -> SuccessResponse:
    existing_stages = await get_full_tournament_details(session, tournament_id)
    check_requirement(existing_stages, user, "max_stages")

    await sql_create_stage(session, tournament_id)
    return SuccessResponse()


@router.put("/tournaments/{tournament_id}/stages/{stage_id}", response_model=SuccessResponse)
async def update_stage(
    session: DbSession,
    tournament_id: TournamentId,
    stage_id: StageId,
    stage_body: StageUpdateBody,
    _: UserPublic = Depends(user_authenticated_for_tournament),
    __: Tournament = Depends(disallow_archived_tournament),
    stage: Stage = Depends(stage_dependency),  # pylint: disable=redefined-builtin
) -> SuccessResponse:
    await sql_update_stage(session, tournament_id, stage_id, stage_body)

    if stage_body.custom_duration_minutes != stage.custom_duration_minutes:
        await schedule_all_matches(session, tournament_id)

    return SuccessResponse()


@router.post("/tournaments/{tournament_id}/stages/activate", response_model=SuccessResponse)
async def activate_next_stage(
    session: DbSession,
    tournament_id: TournamentId,
    stage_body: StageActivateBody,
    _: UserPublic = Depends(user_authenticated_for_tournament),
    __: Tournament = Depends(disallow_archived_tournament),
) -> SuccessResponse:
    stages = await get_full_tournament_details(session, tournament_id)
    active_stage = next((stage for stage in stages if stage.is_active), None)
    if stage_body.direction == "previous" and active_stage is None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="No stage is active yet, so there is no previous stage to go back to",
        )

    new_active_stage = get_adjacent_stage(stages, stage_body.direction)
    if new_active_stage is None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"There is no {stage_body.direction} stage",
        )

    if stage_body.direction == "next":
        await update_matches_in_activated_stage(session, tournament_id, stages, new_active_stage.id)
    elif active_stage is not None:
        results = count_results_in_stage(active_stage)
        if results > 0 and not stage_body.discard_results:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=(
                    f"Going back discards the {results} "
                    f"{'result' if results == 1 else 'results'} of {active_stage.name}. "
                    "Confirm that they can be discarded."
                ),
            )
        await update_matches_in_deactivated_stage(session, tournament_id, active_stage)

    await sql_activate_next_stage(session, new_active_stage.id, tournament_id)
    if stage_body.direction == "previous":
        stages = await get_full_tournament_details(session, tournament_id)
    await handle_conflicts(session, stages)
    return SuccessResponse()


@router.get(
    "/tournaments/{tournament_id}/available_inputs",
    response_model=StageItemInputOptionsResponse,
)
async def get_available_inputs(
    session: DbSession,
    tournament_id: TournamentId,
    _: UserPublic = Depends(user_authenticated_for_tournament),
) -> StageItemInputOptionsResponse:
    stages = await get_full_tournament_details(session, tournament_id)
    teams = await get_teams_with_members(session, tournament_id)
    return StageItemInputOptionsResponse(data=determine_available_inputs(teams, stages))


@router.get("/tournaments/{tournament_id}/next_stage_rankings")
async def get_next_stage_rankings(
    session: DbSession,
    tournament_id: TournamentId,
    _: UserPublic = Depends(user_authenticated_for_tournament),
) -> StageRankingResponse:
    """
    Get the teams that take the slots of the next stage once it is activated.

    A slot that can't be decided yet is left out: its source ranks fewer teams than the position
    the slot takes. `tied_team` names a team that is level on every criterion with the one that
    gets the slot, which only seeding put behind it.
    """
    stages = await get_full_tournament_details(session, tournament_id, with_team_totals=True)
    next_stage = get_adjacent_stage(stages, "next")

    if next_stage is None:
        return StageRankingResponse(data={})

    return StageRankingResponse(
        data=await get_updates_to_inputs_in_activated_stage(
            session, tournament_id, stages, next_stage.id
        )
    )
