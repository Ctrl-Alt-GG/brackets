from fastapi import APIRouter, Depends, HTTPException
from starlette import status

from bracket.config import config
from bracket.database import DbConnection
from bracket.logic.planning.matches import schedule_all_matches
from bracket.logic.ranking.calculation import (
    recalculate_ranking_for_stage_item,
)
from bracket.logic.ranking.elimination import update_inputs_in_subsequent_elimination_rounds
from bracket.models.db.match import (
    Match,
    MatchBody,
    MatchCreateBody,
    MatchCreateBodyFrontend,
)
from bracket.models.db.stage_item import StageType
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
    await check_foreign_keys_belong_to_tournament(conn, match_body, tournament_id)
    await sql_update_match(conn, match_id, match_body)

    round_ = await get_round_by_id(conn, tournament_id, match.round_id)
    stage_item = await get_stage_item(conn, tournament_id, round_.stage_item_id)
    await recalculate_ranking_for_stage_item(conn, tournament_id, stage_item)

    if (
        match_body.custom_duration_minutes != match.custom_duration_minutes
        or match_body.custom_margin_minutes != match.custom_margin_minutes
    ):
        await schedule_all_matches(conn, tournament_id)

    if stage_item.type == StageType.SINGLE_ELIMINATION:
        await update_inputs_in_subsequent_elimination_rounds(
            conn, round_.id, stage_item, {match_id}
        )

    return SuccessResponse()
