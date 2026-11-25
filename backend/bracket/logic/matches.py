"""Recording results, and the matches of Swiss drafts."""

from fastapi import HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from starlette import status

from bracket.logic.planning.matches import schedule_all_matches
from bracket.logic.ranking.calculation import recalculate_ranking_for_stage_item
from bracket.logic.ranking.elimination import update_inputs_in_subsequent_elimination_rounds
from bracket.logic.tournament_graph import TournamentGraph
from bracket.models.db.match import Match, MatchBody, MatchCreateBody, MatchCreateBodyFrontend
from bracket.models.db.stage_item_inputs import StageItemInputFinal
from bracket.models.db.tournament import Tournament
from bracket.models.enums import StageType
from bracket.sql.matches import (
    sql_create_matches,
    sql_delete_match,
    sql_get_match,
    sql_update_match,
)
from bracket.sql.stage_items import get_stage_item
from bracket.sql.stages import get_full_tournament_details
from bracket.sql.validation import validate_match_create
from bracket.utils.i18n import gettext


async def record_match_result(
    session: AsyncSession, tournament: Tournament, match: Match, body: MatchBody
) -> None:
    """
    Save a match's result and custom timing, and everything that follows from them: the later
    matches of a knockout bracket, the schedule, and the standings.

    Correcting a knockout result empties the later matches the previous winner had reached, with
    their results, before the schedule and standings are worked out. The winner's next match can
    move, when the winner plays elsewhere at the time it was planned for.
    """
    graph = TournamentGraph(await get_full_tournament_details(session, tournament.id))
    stage_item, round_ = graph.locate_round(match.round_id)
    current_match = graph.match(match.id)
    is_knockout = stage_item.type is StageType.SINGLE_ELIMINATION

    # Saving 0-0 takes a result back, which is always possible.
    if body.has_result and not all(
        isinstance(input_, StageItemInputFinal)
        for input_ in (current_match.stage_item_input1, current_match.stage_item_input2)
    ):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=gettext("A match can only get a result once both of its teams are known"),
        )

    if (
        is_knockout
        and body.has_result
        and body.stage_item_input1_score == body.stage_item_input2_score
    ):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=gettext(
                "A knockout match needs a winner. Enter the score after overtime or the tiebreak."
            ),
        )

    timing_changes = (body.custom_duration_minutes, body.custom_margin_minutes) != (
        current_match.custom_duration_minutes,
        current_match.custom_margin_minutes,
    )
    await sql_update_match(session, match.id, body)
    graph.update_match(match.id, **body.model_dump())

    if is_knockout:
        await update_inputs_in_subsequent_elimination_rounds(
            session, graph, stage_item, round_.id, {match.id}
        )

    if timing_changes or is_knockout:
        await schedule_all_matches(session, tournament.id, graph=graph, tournament=tournament)

    await recalculate_ranking_for_stage_item(session, tournament.id, stage_item)


async def create_swiss_match(
    session: AsyncSession, tournament: Tournament, body: MatchCreateBodyFrontend
) -> Match:
    """Add a match between two teams to the draft round of a Swiss stage item."""
    round_metadata = await validate_match_create(session, tournament.id, body)
    stage_item = await get_stage_item(session, tournament.id, round_metadata.stage_item_id)
    round_ = next(round_ for round_ in stage_item.rounds if round_.id == round_metadata.id)

    if not round_.is_draft or stage_item.type is not StageType.SWISS:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=gettext("Can only create matches in draft rounds of Swiss stage items"),
        )

    input_ids = [body.stage_item_input1_id, body.stage_item_input2_id]
    local_inputs = {
        input_.id for input_ in stage_item.inputs if isinstance(input_, StageItemInputFinal)
    }
    if any(input_id not in local_inputs for input_id in input_ids):
        raise HTTPException(400, gettext("Choose two assigned teams from this round's stage item"))
    if (
        body.stage_item_input1_winner_from_match_id is not None
        or body.stage_item_input2_winner_from_match_id is not None
    ):
        raise HTTPException(
            400, gettext("Swiss matches use assigned teams, not winners of other matches")
        )
    if input_ids[0] is not None and input_ids[0] == input_ids[1]:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=gettext("A team can't play against itself"),
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
            detail=gettext("One of these teams already has a match in this round"),
        )

    [match] = await sql_create_matches(
        session,
        tournament.id,
        [
            MatchCreateBody(
                **body.model_dump(),
                duration_minutes=tournament.duration_minutes,
                margin_minutes=tournament.margin_minutes,
            )
        ],
    )
    await schedule_all_matches(session, tournament.id, tournament=tournament)
    return await sql_get_match(session, match.id)


async def delete_swiss_match(session: AsyncSession, tournament: Tournament, match: Match) -> None:
    """Remove a match from the draft round of a Swiss stage item."""
    graph = TournamentGraph(await get_full_tournament_details(session, tournament.id))
    stage_item, round_ = graph.locate_round(match.round_id)
    if not round_.is_draft or stage_item.type is not StageType.SWISS:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=gettext("Can only delete matches from draft rounds in Swiss stage items"),
        )

    await sql_delete_match(session, match.id)
    # Draft rounds don't count towards the standings, so the loaded stage item ranks the same.
    await recalculate_ranking_for_stage_item(session, tournament.id, stage_item)
    await schedule_all_matches(session, tournament.id, tournament=tournament)
