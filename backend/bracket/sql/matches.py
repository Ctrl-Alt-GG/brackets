from collections.abc import Sequence
from datetime import datetime

from bracket.database import database
from bracket.models.db.match import Match, MatchBody, MatchCreateBody, MatchTiming
from bracket.models.db.tournament import Tournament
from bracket.utils.id_types import (
    MatchId,
    RoundId,
    StageItemId,
    StageItemInputId,
    TournamentId,
)


async def sql_delete_match(match_id: MatchId) -> None:
    query = """
        DELETE FROM matches
        WHERE matches.id = :match_id
        """
    await database.execute(query=query, values={"match_id": match_id})


async def sql_delete_matches_for_stage_item_id(stage_item_id: StageItemId) -> None:
    query = """
        DELETE FROM matches
        WHERE matches.id IN (
            SELECT matches.id
            FROM matches
            LEFT JOIN rounds ON matches.round_id = rounds.id
            WHERE rounds.stage_item_id = :stage_item_id
        )
        """
    await database.execute(query=query, values={"stage_item_id": stage_item_id})


async def sql_create_match(match: MatchCreateBody) -> Match:
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
    result = await database.fetch_one(query=query, values=match.model_dump())

    if result is None:
        raise ValueError("Could not create stage")

    return Match.model_validate(dict(result._mapping))


async def sql_update_match(match_id: MatchId, match: MatchBody, tournament: Tournament) -> None:
    query = """
        UPDATE matches
        SET round_id = :round_id,
            stage_item_input1_score = :stage_item_input1_score,
            stage_item_input2_score = :stage_item_input2_score,
            custom_duration_minutes = :custom_duration_minutes,
            custom_margin_minutes = :custom_margin_minutes,
            duration_minutes = :duration_minutes,
            margin_minutes = :margin_minutes
        WHERE matches.id = :match_id
        RETURNING *
        """

    duration_minutes = (
        match.custom_duration_minutes
        if match.custom_duration_minutes is not None
        else tournament.duration_minutes
    )
    margin_minutes = (
        match.custom_margin_minutes
        if match.custom_margin_minutes is not None
        else tournament.margin_minutes
    )
    await database.execute(
        query=query,
        values={
            "match_id": match_id,
            **match.model_dump(),
            "duration_minutes": duration_minutes,
            "margin_minutes": margin_minutes,
        },
    )


async def sql_set_input_ids_for_match(
    round_id: RoundId, match_id: MatchId, input_ids: list[StageItemInputId | None]
) -> None:
    query = """
        UPDATE matches
        SET stage_item_input1_id = :input1_id,
            stage_item_input2_id = :input2_id
        WHERE round_id = :round_id
        AND matches.id = :match_id
        """
    await database.execute(
        query=query,
        values={
            "round_id": round_id,
            "match_id": match_id,
            "input1_id": input_ids[0],
            "input2_id": input_ids[1],
        },
    )


async def sql_update_match_timings(timings: Sequence[MatchTiming]) -> None:
    if len(timings) < 1:
        return

    query = """
        UPDATE matches
        SET start_time = :start_time,
            duration_minutes = :duration_minutes,
            margin_minutes = :margin_minutes
        WHERE matches.id = :match_id
        """
    await database.execute_many(
        query=query,
        values=[
            {
                "match_id": timing.match_id,
                "start_time": datetime.fromisoformat(timing.start_time.isoformat()),
                "duration_minutes": timing.duration_minutes,
                "margin_minutes": timing.margin_minutes,
            }
            for timing in timings
        ],
    )


async def sql_get_match(match_id: MatchId) -> Match:
    query = """
        SELECT *
        FROM matches
        WHERE matches.id = :match_id
        """
    result = await database.fetch_one(query=query, values={"match_id": match_id})

    if result is None:
        raise ValueError("Could not create stage")

    return Match.model_validate(dict(result._mapping))


async def clear_scores_for_matches_in_stage_item(
    tournament_id: TournamentId, stage_item_id: StageItemId
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
    await database.execute(
        query=query,
        values={
            "stage_item_id": stage_item_id,
            "tournament_id": tournament_id,
        },
    )
