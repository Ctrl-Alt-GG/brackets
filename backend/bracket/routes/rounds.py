from fastapi import APIRouter, Depends, HTTPException
from heliclockter import datetime_utc
from sqlalchemy import text
from starlette import status

from bracket.config import config
from bracket.database import DbConnection
from bracket.logic.planning.matches import schedule_all_matches
from bracket.logic.planning.rounds import get_draft_round
from bracket.logic.ranking.calculation import (
    recalculate_ranking_for_stage_item,
)
from bracket.logic.scheduling.swiss import get_swiss_pairing
from bracket.logic.subscriptions import check_requirement
from bracket.models.db.match import MatchCreateBody
from bracket.models.db.round import (
    Round,
    RoundCreateBody,
    RoundInsertable,
    RoundUpdateBody,
)
from bracket.models.db.tournament import Tournament
from bracket.models.db.user import UserPublic
from bracket.models.db.util import RoundWithMatches
from bracket.routes.auth import user_authenticated_for_tournament
from bracket.routes.models import SuccessResponse
from bracket.routes.util import (
    disallow_archived_tournament,
    round_dependency,
    round_with_matches_dependency,
)
from bracket.sql.matches import sql_create_match, sql_delete_match
from bracket.sql.rounds import (
    get_next_round_name,
    sql_create_round,
    sql_delete_round,
)
from bracket.sql.stage_items import get_stage_item
from bracket.sql.stages import get_full_tournament_details
from bracket.sql.validation import check_foreign_keys_belong_to_tournament
from bracket.utils.id_types import RoundId, TournamentId

router = APIRouter(prefix=config.api_prefix)


@router.delete("/tournaments/{tournament_id}/rounds/{round_id}", response_model=SuccessResponse)
async def delete_round(
    conn: DbConnection,
    tournament_id: TournamentId,
    round_id: RoundId,
    _: UserPublic = Depends(user_authenticated_for_tournament),
    __: Tournament = Depends(disallow_archived_tournament),
    round_with_matches: RoundWithMatches = Depends(round_with_matches_dependency),
) -> SuccessResponse:
    for match in round_with_matches.matches:
        await sql_delete_match(conn, match.id)

    await sql_delete_round(conn, round_id)

    stage_item = await get_stage_item(conn, tournament_id, round_with_matches.stage_item_id)
    await recalculate_ranking_for_stage_item(conn, tournament_id, stage_item)
    await schedule_all_matches(conn, tournament_id)
    return SuccessResponse()


@router.post("/tournaments/{tournament_id}/rounds", response_model=SuccessResponse)
async def create_round(
    conn: DbConnection,
    tournament_id: TournamentId,
    round_body: RoundCreateBody,
    user: UserPublic = Depends(user_authenticated_for_tournament),
    tournament: Tournament = Depends(disallow_archived_tournament),
) -> SuccessResponse:
    """
    Create the next round of a Swiss stage item as a draft in which every active team is paired.

    Only organizers see the draft. Its pairings can be changed by adding and deleting matches, and
    it is published by updating the round with `is_draft` set to false.
    """
    await check_foreign_keys_belong_to_tournament(conn, round_body, tournament_id)

    stages = await get_full_tournament_details(conn, tournament_id)
    existing_rounds = [
        round_
        for stage in stages
        for stage_item in stage.stage_items
        for round_ in stage_item.rounds
    ]
    check_requirement(existing_rounds, user, "max_rounds")

    stage_item = await get_stage_item(conn, tournament_id, stage_item_id=round_body.stage_item_id)

    if not stage_item.type.supports_dynamic_number_of_rounds:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=(
                f"Rounds of {stage_item.type_name.lower()} stage items are created automatically"
            ),
        )

    if (draft_round := get_draft_round(stage_item)) is not None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Publish or discard the draft {draft_round.name} first",
        )

    pairing = get_swiss_pairing(stage_item)
    if len(pairing.pairs) < 1:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=(
                "Assign at least two active teams to this stage item first"
                if len(pairing.unpaired) < 2
                else "Every team has already played every other team"
            ),
        )

    round_id = await sql_create_round(
        conn,
        RoundInsertable(
            created=datetime_utc.now(),
            is_draft=True,
            stage_item_id=stage_item.id,
            name=round_body.name or await get_next_round_name(conn, tournament_id, stage_item.id),
        ),
    )
    for input1, input2 in pairing.pairs:
        await sql_create_match(
            conn,
            MatchCreateBody(
                round_id=round_id,
                stage_item_input1_id=input1.id,
                stage_item_input2_id=input2.id,
                stage_item_input1_winner_from_match_id=None,
                stage_item_input2_winner_from_match_id=None,
                duration_minutes=tournament.duration_minutes,
                margin_minutes=tournament.margin_minutes,
                custom_duration_minutes=None,
                custom_margin_minutes=None,
            ),
        )

    await schedule_all_matches(conn, tournament_id)
    return SuccessResponse()


@router.put("/tournaments/{tournament_id}/rounds/{round_id}", response_model=SuccessResponse)
async def update_round_by_id(
    conn: DbConnection,
    tournament_id: TournamentId,
    round_id: RoundId,
    round_body: RoundUpdateBody,
    _: UserPublic = Depends(user_authenticated_for_tournament),
    __: Round = Depends(round_dependency),
    ___: Tournament = Depends(disallow_archived_tournament),
) -> SuccessResponse:
    query = """
        UPDATE rounds
        SET name = :name, is_draft = :is_draft
        WHERE rounds.id IN (
            SELECT rounds.id
            FROM rounds
            JOIN stage_items ON rounds.stage_item_id = stage_items.id
            JOIN stages s on s.id = stage_items.stage_id
            WHERE s.tournament_id = :tournament_id
        )
        AND rounds.id = :round_id
    """
    await conn.execute(
        text(query),
        {
            "tournament_id": tournament_id,
            "round_id": round_id,
            "name": round_body.name,
            "is_draft": round_body.is_draft,
        },
    )
    return SuccessResponse()
