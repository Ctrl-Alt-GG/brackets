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
    query = """
        UPDATE matches
        SET round_id = :round_id,
            stage_item_input1_score = :stage_item_input1_score,
            stage_item_input2_score = :stage_item_input2_score,
            custom_duration_minutes = :custom_duration_minutes,
            custom_margin_minutes = :custom_margin_minutes
        WHERE matches.id = :match_id
        """
    await conn.execute(text(query), {"match_id": match_id, **match.model_dump(exclude_none=False)})


async def sql_set_input_ids_for_match(
    conn: AsyncConnection,
    round_id: RoundId,
    match_id: MatchId,
    input_ids: list[StageItemInputId | None],
) -> None:
    query = """
        UPDATE matches
        SET stage_item_input1_id = :input1_id,
            stage_item_input2_id = :input2_id
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


async def clear_scores_for_matches_in_stage_item(
    conn: AsyncConnection, tournament_id: TournamentId, stage_item_id: StageItemId
) -> None:
    query = """
        UPDATE matches
        SET stage_item_input1_score = 0,
            stage_item_input2_score = 0
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
