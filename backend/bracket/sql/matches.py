from collections.abc import Sequence

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncConnection

from bracket.models.db.match import Match, MatchBody, MatchCreateBody, MatchTiming
from bracket.utils.id_types import (
    MatchId,
    RoundId,
    StageItemId,
    StageItemInputId,
    TournamentId,
)


async def sql_delete_match(conn: AsyncConnection, match_id: MatchId) -> None:
    query = """
        DELETE FROM matches
        WHERE matches.id = :match_id
        """
    await conn.execute(text(query), {"match_id": match_id})


async def sql_delete_matches_for_stage_item_id(
    conn: AsyncConnection, stage_item_id: StageItemId
) -> None:
    query = """
        DELETE FROM matches
        WHERE matches.id IN (
            SELECT matches.id
            FROM matches
            LEFT JOIN rounds ON matches.round_id = rounds.id
            WHERE rounds.stage_item_id = :stage_item_id
        )
        """
    await conn.execute(text(query), {"stage_item_id": stage_item_id})


async def sql_create_match(conn: AsyncConnection, match: MatchCreateBody) -> Match:
    query = """
        INSERT INTO matches (
            round_id,
            stage_item_input1_id,
            stage_item_input2_id,
            stage_item_input1_winner_from_match_id,
            stage_item_input2_winner_from_match_id,
            duration_minutes,
            custom_duration_minutes,
            margin_minutes,
            custom_margin_minutes,
            stage_item_input1_score,
            stage_item_input2_score,
            stage_item_input1_conflict,
            stage_item_input2_conflict,
            created
        )
        VALUES (
            :round_id,
            :stage_item_input1_id,
            :stage_item_input2_id,
            :stage_item_input1_winner_from_match_id,
            :stage_item_input2_winner_from_match_id,
            :duration_minutes,
            :custom_duration_minutes,
            :margin_minutes,
            :custom_margin_minutes,
            0,
            0,
            false,
            false,
            NOW()
        )
        RETURNING *
    """
    result = (await conn.execute(text(query), match.model_dump(exclude_none=False))).first()

    if result is None:
        raise ValueError("Could not create stage")

    return Match.model_validate(result._mapping)


async def sql_update_match(conn: AsyncConnection, match_id: MatchId, match: MatchBody) -> None:
    """Save a result. The match stays in its round: scores never move it."""
    query = """
        UPDATE matches
        SET stage_item_input1_score = :stage_item_input1_score,
            stage_item_input2_score = :stage_item_input2_score,
            scoreless_result = :scoreless_result,
            custom_duration_minutes = :custom_duration_minutes,
            custom_margin_minutes = :custom_margin_minutes
        WHERE matches.id = :match_id
        """
    has_score = match.stage_item_input1_score != 0 or match.stage_item_input2_score != 0
    await conn.execute(
        text(query),
        {
            "match_id": match_id,
            "stage_item_input1_score": match.stage_item_input1_score,
            "stage_item_input2_score": match.stage_item_input2_score,
            # Only a 0-0 needs the marker; a score is a result by itself.
            "scoreless_result": match.scoreless_result and not has_score,
            "custom_duration_minutes": match.custom_duration_minutes,
            "custom_margin_minutes": match.custom_margin_minutes,
        },
    )


async def sql_set_input_ids_for_match(
    conn: AsyncConnection,
    round_id: RoundId,
    match_id: MatchId,
    input_ids: list[StageItemInputId | None],
    *,
    reset_result: bool = False,
) -> None:
    """Set who plays a match. `reset_result` also discards its result, which was between others."""
    reset = (
        """,
            stage_item_input1_score = 0,
            stage_item_input2_score = 0,
            scoreless_result = false"""
        if reset_result
        else ""
    )
    query = f"""
        UPDATE matches
        SET stage_item_input1_id = :input1_id,
            stage_item_input2_id = :input2_id{reset}
        WHERE round_id = :round_id
        AND matches.id = :match_id
        """
    await conn.execute(
        text(query),
        {
            "round_id": round_id,
            "match_id": match_id,
            "input1_id": input_ids[0],
            "input2_id": input_ids[1],
        },
    )


async def sql_add_margin_to_matches(
    conn: AsyncConnection, match_ids: Sequence[MatchId], default_margin_minutes: int, minutes: int
) -> None:
    """Lengthen (or shorten) the break after these matches, which moves everything after them."""
    if len(match_ids) < 1:
        return

    query = """
        UPDATE matches
        SET custom_margin_minutes = GREATEST(
            0, COALESCE(custom_margin_minutes, :default_margin_minutes) + :minutes
        )
        WHERE matches.id = any(:match_ids)
        """
    await conn.execute(
        text(query),
        {
            "match_ids": list(match_ids),
            "default_margin_minutes": default_margin_minutes,
            "minutes": minutes,
        },
    )


async def sql_update_match_timings(conn: AsyncConnection, timings: Sequence[MatchTiming]) -> None:
    if len(timings) < 1:
        return

    query = """
        UPDATE matches
        SET start_time = :start_time,
            duration_minutes = :duration_minutes,
            margin_minutes = :margin_minutes
        WHERE matches.id = :match_id
        """
    await conn.execute(
        text(query),
        [
            {
                "match_id": timing.match_id,
                "start_time": timing.start_time,
                "duration_minutes": timing.duration_minutes,
                "margin_minutes": timing.margin_minutes,
            }
            for timing in timings
        ],
    )


async def sql_get_match(conn: AsyncConnection, match_id: MatchId) -> Match:
    query = """
        SELECT *
        FROM matches
        WHERE matches.id = :match_id
        """
    result = (await conn.execute(text(query), {"match_id": match_id})).first()

    if result is None:
        raise ValueError("Could not create stage")

    return Match.model_validate(result._mapping)


async def clear_results_for_matches_in_stage_item(
    conn: AsyncConnection, tournament_id: TournamentId, stage_item_id: StageItemId
) -> None:
    query = """
        UPDATE matches
        SET stage_item_input1_score = 0,
            stage_item_input2_score = 0,
            scoreless_result = false
        FROM rounds
        JOIN stage_items ON rounds.stage_item_id = stage_items.id
        JOIN stages ON stages.id = stage_items.stage_id
        WHERE   rounds.id = matches.round_id
            AND stages.tournament_id = :tournament_id
            AND stage_items.id = :stage_item_id
        """
    await conn.execute(
        text(query), {"stage_item_id": stage_item_id, "tournament_id": tournament_id}
    )
