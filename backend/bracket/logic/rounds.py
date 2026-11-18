"""The rounds of Swiss stage items, which are drawn, published and deleted one at a time."""

from fastapi import HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from starlette import status
from starlette.concurrency import run_in_threadpool

from bracket import orm
from bracket.logic.planning.matches import schedule_all_matches
from bracket.logic.ranking.calculation import recalculate_ranking_for_stage_item
from bracket.logic.scheduling.swiss import SwissPairing, get_swiss_pairing
from bracket.logic.subscriptions import Limit, check_requirement
from bracket.models.db.match import MatchCreateBody, is_played
from bracket.models.db.round import Round, RoundCreateBody, RoundUpdateBody
from bracket.models.db.stage_tree import RoundWithMatches, StageItemWithRounds
from bracket.models.db.tournament import Tournament
from bracket.models.db.user import UserPublic
from bracket.sql.matches import sql_create_matches, sql_delete_matches
from bracket.sql.rounds import (
    get_next_round_name,
    sql_create_rounds,
    sql_delete_round,
    sql_update_round,
)
from bracket.sql.stage_items import get_stage_item
from bracket.sql.tournaments import count_tournament_records
from bracket.sql.validation import validate_round_create
from bracket.utils.id_types import RoundId, TournamentId


def get_draft_round(stage_item: StageItemWithRounds) -> RoundWithMatches | None:
    return next(
        (round_ for round_ in sorted(stage_item.rounds, key=lambda r: r.id) if round_.is_draft),
        None,
    )


async def write_swiss_pairings(
    session: AsyncSession, tournament: Tournament, round_id: RoundId, pairing: SwissPairing
) -> None:
    await sql_create_matches(
        session,
        tournament.id,
        [
            MatchCreateBody(
                round_id=round_id,
                stage_item_input1_id=input1.id,
                stage_item_input2_id=input2.id,
                duration_minutes=tournament.duration_minutes,
                margin_minutes=tournament.margin_minutes,
            )
            for input1, input2 in pairing.pairs
        ],
    )


async def create_swiss_round(
    session: AsyncSession, tournament: Tournament, body: RoundCreateBody, user: UserPublic
) -> None:
    """
    Create the next round of a Swiss stage item as a draft in which every active team is paired.
    """
    await validate_round_create(session, tournament.id, body)
    check_requirement(
        Limit.ROUNDS, await count_tournament_records(session, orm.Round, tournament.id), user
    )

    stage_item = await get_stage_item(session, tournament.id, stage_item_id=body.stage_item_id)
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

    # The pairing search is the heaviest computation of the app. In a worker thread, other
    # requests are still answered while it runs.
    pairing = await run_in_threadpool(get_swiss_pairing, stage_item)
    if len(pairing.pairs) < 1:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=(
                "Assign at least two active teams to this stage item first"
                if len(pairing.unpaired) < 2
                else "Every team has already played every other team"
            ),
        )

    name = body.name or await get_next_round_name(session, tournament.id, stage_item.id)
    [round_id] = await sql_create_rounds(
        session, tournament.id, stage_item.id, [name], is_draft=True
    )
    await write_swiss_pairings(session, tournament, round_id, pairing)
    await schedule_all_matches(session, tournament.id, tournament=tournament)


async def regenerate_swiss_round(
    session: AsyncSession, tournament: Tournament, round_: RoundWithMatches
) -> None:
    """Replace the pairings of a Swiss draft, keeping the draft if no replacement is possible."""
    stage_item = await get_stage_item(session, tournament.id, round_.stage_item_id)
    if not round_.is_draft or not stage_item.type.supports_dynamic_number_of_rounds:
        raise HTTPException(400, "Only a draft Swiss round can be regenerated")
    if any(is_played(match) for match in round_.matches):
        raise HTTPException(400, "Clear the draft's results before regenerating its pairings")

    previous_rounds = stage_item.model_copy(
        update={
            "rounds": [candidate for candidate in stage_item.rounds if candidate.id != round_.id]
        }
    )
    pairing = await run_in_threadpool(get_swiss_pairing, previous_rounds)
    if not pairing.pairs:
        raise HTTPException(400, "No replacement pairings are available. The draft was kept.")

    await sql_delete_matches(session, [match.id for match in round_.matches])
    await write_swiss_pairings(session, tournament, round_.id, pairing)
    # Draft rounds don't count towards the standings, so the loaded stage item ranks the same.
    await recalculate_ranking_for_stage_item(session, tournament.id, stage_item)
    await schedule_all_matches(session, tournament.id, tournament=tournament)


async def delete_swiss_round(
    session: AsyncSession, tournament: Tournament, round_: RoundWithMatches
) -> None:
    stage_item = await get_stage_item(session, tournament.id, round_.stage_item_id)
    if not stage_item.type.supports_dynamic_number_of_rounds:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=(
                f"The rounds of a {stage_item.type_name.lower()} belong to its format and "
                "can't be deleted"
            ),
        )

    await sql_delete_matches(session, [match.id for match in round_.matches])
    await sql_delete_round(session, round_.id)

    remaining = stage_item.model_copy(
        update={
            "rounds": [candidate for candidate in stage_item.rounds if candidate.id != round_.id]
        }
    )
    await recalculate_ranking_for_stage_item(session, tournament.id, remaining)
    await schedule_all_matches(session, tournament.id, tournament=tournament)


async def update_round(
    session: AsyncSession, tournament_id: TournamentId, round_: Round, body: RoundUpdateBody
) -> None:
    """
    Rename a round, or publish or withdraw a draft. Only Swiss rounds can be drafts: the rounds of
    the other formats are published with their stage item, and a withdrawn one couldn't be
    published again.
    """
    publication_changes = body.is_draft != round_.is_draft
    stage_item = await get_stage_item(session, tournament_id, round_.stage_item_id)
    if publication_changes and not stage_item.type.supports_dynamic_number_of_rounds:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=(
                f"The rounds of a {stage_item.type_name.lower()} are always published. Only "
                "Swiss rounds can be drafts."
            ),
        )

    await sql_update_round(session, tournament_id, round_.id, body)

    # Only published rounds count, so publishing a round or taking it back changes the standings.
    if publication_changes:
        for candidate in stage_item.rounds:
            if candidate.id == round_.id:
                candidate.is_draft = body.is_draft
        await recalculate_ranking_for_stage_item(session, tournament_id, stage_item)
