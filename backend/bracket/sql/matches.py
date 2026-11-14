from collections.abc import Sequence

from sqlalchemy import delete, func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from bracket import orm
from bracket.models.db.match import Match, MatchBody, MatchCreateBody, MatchInsertable, MatchTiming
from bracket.utils.id_types import (
    MatchId,
    RoundId,
    StageItemId,
    StageItemInputId,
    TournamentId,
)


def match_without_details(entity: orm.Match) -> Match:
    """The result-edit response contains match columns; nested slots belong to stage reads."""
    return Match.model_validate(
        {name: getattr(entity, name) for name in ("id", *MatchInsertable.model_fields)}
    )


async def sql_delete_match(conn: AsyncSession, match_id: MatchId) -> None:
    await conn.execute(delete(orm.Match).where(orm.Match.id == match_id))


async def sql_delete_matches_for_stage_item_id(
    conn: AsyncSession, stage_item_id: StageItemId
) -> None:
    await conn.execute(
        delete(orm.Match).where(
            orm.Match.round_id.in_(
                select(orm.Round.id).where(orm.Round.stage_item_id == stage_item_id)
            )
        )
    )


async def sql_create_match(conn: AsyncSession, match: MatchCreateBody) -> Match:
    entity = orm.Match(
        round_id=match.round_id,
        stage_item_input1_id=match.stage_item_input1_id,
        stage_item_input2_id=match.stage_item_input2_id,
        stage_item_input1_winner_from_match_id=match.stage_item_input1_winner_from_match_id,
        stage_item_input2_winner_from_match_id=match.stage_item_input2_winner_from_match_id,
        duration_minutes=match.duration_minutes,
        custom_duration_minutes=match.custom_duration_minutes,
        margin_minutes=match.margin_minutes,
        custom_margin_minutes=match.custom_margin_minutes,
        stage_item_input1_score=0,
        stage_item_input2_score=0,
        stage_item_input1_conflict=False,
        stage_item_input2_conflict=False,
    )
    conn.add(entity)
    await conn.flush()
    return match_without_details(entity)


async def sql_update_match(conn: AsyncSession, match_id: MatchId, match: MatchBody) -> None:
    """Save a result. The match stays in its round: scores never move it."""
    has_score = match.stage_item_input1_score != 0 or match.stage_item_input2_score != 0
    await conn.execute(
        update(orm.Match)
        .where(orm.Match.id == match_id)
        .values(
            stage_item_input1_score=match.stage_item_input1_score,
            stage_item_input2_score=match.stage_item_input2_score,
            scoreless_result=match.scoreless_result and not has_score,
            custom_duration_minutes=match.custom_duration_minutes,
            custom_margin_minutes=match.custom_margin_minutes,
        )
    )


async def sql_set_input_ids_for_match(
    conn: AsyncSession,
    round_id: RoundId,
    match_id: MatchId,
    input_ids: list[StageItemInputId | None],
    *,
    reset_result: bool = False,
) -> None:
    """Set competitors, discarding the previous competitors' result when requested."""
    statement = update(orm.Match).where(orm.Match.round_id == round_id, orm.Match.id == match_id)
    if reset_result:
        statement = statement.values(
            stage_item_input1_score=0, stage_item_input2_score=0, scoreless_result=False
        )
    await conn.execute(
        statement.values(stage_item_input1_id=input_ids[0], stage_item_input2_id=input_ids[1])
    )


async def sql_add_margin_to_matches(
    conn: AsyncSession, match_ids: Sequence[MatchId], default_margin_minutes: int, minutes: int
) -> None:
    """Lengthen or shorten breaks, moving the matches scheduled after them."""
    if not match_ids:
        return
    await conn.execute(
        update(orm.Match)
        .where(orm.Match.id.in_(match_ids))
        .values(
            custom_margin_minutes=func.greatest(
                0, func.coalesce(orm.Match.custom_margin_minutes, default_margin_minutes) + minutes
            )
        )
    )


async def sql_update_match_timings(conn: AsyncSession, timings: Sequence[MatchTiming]) -> None:
    if not timings:
        return
    await conn.execute(
        update(orm.Match),
        [
            {
                "id": timing.match_id,
                "start_time": timing.start_time,
                "duration_minutes": timing.duration_minutes,
                "margin_minutes": timing.margin_minutes,
            }
            for timing in timings
        ],
    )


async def sql_get_match(conn: AsyncSession, match_id: MatchId) -> Match:
    entity = await conn.get(orm.Match, match_id, populate_existing=True)
    if entity is None:
        raise ValueError("Match not found")
    return match_without_details(entity)


async def clear_results_for_matches_in_stage_item(
    conn: AsyncSession, tournament_id: TournamentId, stage_item_id: StageItemId
) -> None:
    round_ids = (
        select(orm.Round.id)
        .join(orm.StageItem, orm.StageItem.id == orm.Round.stage_item_id)
        .join(orm.Stage, orm.Stage.id == orm.StageItem.stage_id)
        .where(orm.StageItem.id == stage_item_id, orm.Stage.tournament_id == tournament_id)
    )
    await conn.execute(
        update(orm.Match)
        .where(orm.Match.round_id.in_(round_ids))
        .values(stage_item_input1_score=0, stage_item_input2_score=0, scoreless_result=False)
    )
