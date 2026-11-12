from fastapi import APIRouter, Depends, HTTPException
from starlette import status

from bracket.config import config
from bracket.database import DbConnection
from bracket.logic.planning.conflicts import handle_conflicts
from bracket.logic.planning.matches import delay_upcoming_matches, schedule_all_matches
from bracket.logic.ranking.calculation import (
    recalculate_ranking_for_stage_item,
)
from bracket.logic.ranking.elimination import update_inputs_in_subsequent_elimination_rounds
from bracket.models.db.match import (
    Match,
    MatchBody,
    MatchCreateBody,
    MatchCreateBodyFrontend,
    ScheduleDelayBody,
)
from bracket.models.db.stage_item import StageType
from bracket.models.db.stage_item_inputs import StageItemInputFinal
from bracket.models.db.tournament import Tournament
from bracket.models.db.user import UserPublic
from bracket.routes.auth import user_authenticated_for_tournament
from bracket.routes.models import SingleMatchResponse, SuccessResponse
from bracket.routes.util import disallow_archived_tournament, match_dependency
from bracket.sql.matches import (
    sql_create_match,
    sql_delete_match,
    sql_get_match,
    sql_update_match,
)
from bracket.sql.rounds import get_round_by_id
from bracket.sql.stage_items import get_stage_item
from bracket.sql.stages import get_full_tournament_details
from bracket.sql.tournaments import sql_get_tournament
from bracket.sql.validation import check_foreign_keys_belong_to_tournament
from bracket.utils.id_types import MatchId, TournamentId

router = APIRouter(prefix=config.api_prefix)


@router.delete("/tournaments/{tournament_id}/matches/{match_id}", response_model=SuccessResponse)
async def delete_match(
    conn: DbConnection,
    tournament_id: TournamentId,
    _: UserPublic = Depends(user_authenticated_for_tournament),
    __: Tournament = Depends(disallow_archived_tournament),
    match: Match = Depends(match_dependency),
) -> SuccessResponse:
    round_ = await get_round_by_id(conn, tournament_id, match.round_id)
    stage_item = await get_stage_item(conn, tournament_id, round_.stage_item_id)

    if not round_.is_draft or stage_item.type != StageType.SWISS:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Can only delete matches from draft rounds in Swiss stage items",
        )

    await sql_delete_match(conn, match.id)

    stage_item = await get_stage_item(conn, tournament_id, round_.stage_item_id)

    await recalculate_ranking_for_stage_item(conn, tournament_id, stage_item)
    await schedule_all_matches(conn, tournament_id)
    return SuccessResponse()


@router.post("/tournaments/{tournament_id}/matches", response_model=SingleMatchResponse)
async def create_match(
    conn: DbConnection,
    tournament_id: TournamentId,
    match_body: MatchCreateBodyFrontend,
    _: UserPublic = Depends(user_authenticated_for_tournament),
    __: Tournament = Depends(disallow_archived_tournament),
) -> SingleMatchResponse:
    await check_foreign_keys_belong_to_tournament(conn, match_body, tournament_id)

    round_ = await get_round_by_id(conn, tournament_id, match_body.round_id)
    stage_item = await get_stage_item(conn, tournament_id, round_.stage_item_id)

    if not round_.is_draft or stage_item.type != StageType.SWISS:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Can only create matches in draft rounds of Swiss stage items",
        )

    input_ids = [match_body.stage_item_input1_id, match_body.stage_item_input2_id]
    local_inputs = {
        input_.id for input_ in stage_item.inputs if isinstance(input_, StageItemInputFinal)
    }
    if any(input_id not in local_inputs for input_id in input_ids):
        raise HTTPException(400, "Choose two assigned teams from this round's stage item")
    if (
        match_body.stage_item_input1_winner_from_match_id is not None
        or match_body.stage_item_input2_winner_from_match_id is not None
    ):
        raise HTTPException(400, "Swiss matches use assigned teams, not winners of other matches")
    if input_ids[0] is not None and input_ids[0] == input_ids[1]:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="A team can't play against itself",
        )

    input_ids_in_round = {
        input_id
        for match in round_.matches
        for input_id in (match.stage_item_input1_id, match.stage_item_input2_id)
        if input_id is not None
    }
    if any(input_id in input_ids_in_round for input_id in input_ids if input_id is not None):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="One of these teams already has a match in this round",
        )

    tournament = await sql_get_tournament(conn, tournament_id)
    body_with_durations = MatchCreateBody(
        **match_body.model_dump(),
        duration_minutes=tournament.duration_minutes,
        margin_minutes=tournament.margin_minutes,
    )

    match = await sql_create_match(conn, body_with_durations)
    await schedule_all_matches(conn, tournament_id)
    return SingleMatchResponse(data=await sql_get_match(conn, match.id))


@router.post("/tournaments/{tournament_id}/schedule_matches", response_model=SuccessResponse)
async def schedule_matches(
    conn: DbConnection,
    tournament_id: TournamentId,
    _: UserPublic = Depends(user_authenticated_for_tournament),
    __: Tournament = Depends(disallow_archived_tournament),
) -> SuccessResponse:
    await schedule_all_matches(conn, tournament_id)
    return SuccessResponse()


@router.post("/tournaments/{tournament_id}/delay_schedule", response_model=SuccessResponse)
async def delay_schedule(
    conn: DbConnection,
    tournament_id: TournamentId,
    body: ScheduleDelayBody,
    _: UserPublic = Depends(user_authenticated_for_tournament),
    __: Tournament = Depends(disallow_archived_tournament),
) -> SuccessResponse:
    """
    Move every round that hasn't been played yet, and everything after it, for an event that
    runs late. A negative number of minutes moves them earlier.
    """
    await delay_upcoming_matches(conn, tournament_id, body.minutes)
    return SuccessResponse()


@router.put("/tournaments/{tournament_id}/matches/{match_id}", response_model=SuccessResponse)
async def update_match_by_id(
    conn: DbConnection,
    tournament_id: TournamentId,
    match_id: MatchId,
    match_body: MatchBody,
    _: UserPublic = Depends(user_authenticated_for_tournament),
    __: Tournament = Depends(disallow_archived_tournament),
    match: Match = Depends(match_dependency),
) -> SuccessResponse:
    round_ = await get_round_by_id(conn, tournament_id, match.round_id)
    stage_item = await get_stage_item(conn, tournament_id, round_.stage_item_id)
    is_knockout = stage_item.type == StageType.SINGLE_ELIMINATION

    is_draw = match_body.stage_item_input1_score == match_body.stage_item_input2_score
    has_result = match_body.stage_item_input1_score != 0 or match_body.scoreless_result
    if is_knockout and is_draw and has_result:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=(
                "A knockout match needs a winner. Enter the score after overtime or the tiebreak."
            ),
        )

    await sql_update_match(conn, match_id, match_body)

    if (
        match_body.custom_duration_minutes != match.custom_duration_minutes
        or match_body.custom_margin_minutes != match.custom_margin_minutes
    ):
        await schedule_all_matches(conn, tournament_id)

    stage_item = await get_stage_item(conn, tournament_id, round_.stage_item_id)
    if is_knockout:
        # A changed winner changes who plays the next match, which discards results further
        # down the bracket. The statistics below are worked out after that.
        await update_inputs_in_subsequent_elimination_rounds(
            conn, round_.id, stage_item, {match_id}
        )
        stage_item = await get_stage_item(conn, tournament_id, round_.stage_item_id)
        await handle_conflicts(conn, await get_full_tournament_details(conn, tournament_id))

    await recalculate_ranking_for_stage_item(conn, tournament_id, stage_item)
    return SuccessResponse()
