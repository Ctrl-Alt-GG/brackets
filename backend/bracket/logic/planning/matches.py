from heliclockter import timedelta
from sqlalchemy.ext.asyncio import AsyncConnection

from bracket.logic.planning.conflicts import handle_conflicts
from bracket.models.db.match import MatchTiming
from bracket.models.db.tournament import Tournament
from bracket.models.db.util import StageWithStageItems
from bracket.sql.matches import sql_update_match_timings
from bracket.sql.stages import get_full_tournament_details
from bracket.sql.tournaments import sql_get_tournament
from bracket.utils.id_types import TournamentId


def plan_match_timings(
    stages: list[StageWithStageItems], tournament: Tournament
) -> list[MatchTiming]:
    """
    Plan when every match of the tournament starts.

    All matches of a round start together, and the next round starts once the longest match of
    the previous round (including its margin) has finished. The stage items of a stage are played
    in parallel, and a stage starts once every stage item of the previous stage has finished.

    The tournament's match duration is a default that a stage can overwrite for its matches. The
    custom duration of a match takes precedence over both.
    """
    timings: list[MatchTiming] = []
    stage_start = tournament.start_time

    for stage in sorted(stages, key=lambda stage: stage.id):
        stage_end = stage_start
        stage_duration_minutes = (
            tournament.duration_minutes
            if stage.custom_duration_minutes is None
            else stage.custom_duration_minutes
        )

        for stage_item in stage.stage_items:
            round_start = stage_start

            for round_ in sorted(stage_item.rounds, key=lambda round_: round_.id):
                round_minutes = 0

                for match in round_.matches:
                    duration_minutes = (
                        stage_duration_minutes
                        if match.custom_duration_minutes is None
                        else match.custom_duration_minutes
                    )
                    margin_minutes = (
                        tournament.margin_minutes
                        if match.custom_margin_minutes is None
                        else match.custom_margin_minutes
                    )
                    timings.append(
                        MatchTiming(
                            match_id=match.id,
                            start_time=round_start,
                            duration_minutes=duration_minutes,
                            margin_minutes=margin_minutes,
                        )
                    )
                    round_minutes = max(round_minutes, duration_minutes + margin_minutes)

                round_start += timedelta(minutes=round_minutes)

            stage_end = max(stage_end, round_start)

        stage_start = stage_end

    return timings


async def schedule_all_matches(conn: AsyncConnection, tournament_id: TournamentId) -> None:
    """
    Update the start time of every match whose planned time has changed.

    Call this whenever rounds or matches are added or removed, or when the tournament's start
    time or any match duration or margin changes.
    """
    tournament = await sql_get_tournament(conn, tournament_id)
    stages = await get_full_tournament_details(conn, tournament_id)
    matches = {
        match.id: match
        for stage in stages
        for stage_item in stage.stage_items
        for round_ in stage_item.rounds
        for match in round_.matches
    }

    changed_timings = [
        timing
        for timing in plan_match_timings(stages, tournament)
        if (
            matches[timing.match_id].start_time,
            matches[timing.match_id].duration_minutes,
            matches[timing.match_id].margin_minutes,
        )
        != (timing.start_time, timing.duration_minutes, timing.margin_minutes)
    ]
    if len(changed_timings) < 1:
        return

    await sql_update_match_timings(conn, changed_timings)
    await handle_conflicts(conn, await get_full_tournament_details(conn, tournament_id))
