from typing import NamedTuple

from fastapi import HTTPException
from heliclockter import datetime_utc, timedelta
from sqlalchemy.ext.asyncio import AsyncSession
from starlette import status

from bracket.logic.planning.calendar import Calendar, Lineups
from bracket.logic.tournament_graph import TournamentGraph
from bracket.models.db.match import MAX_MINUTES, MatchTiming, is_played
from bracket.models.db.stage_tree import RoundWithMatches, StageWithStageItems
from bracket.models.db.tournament import Tournament
from bracket.sql.matches import (
    get_matches_elsewhere,
    sql_add_margin_to_matches,
    sql_update_match_timings,
)
from bracket.sql.participation import get_lineups
from bracket.sql.stages import get_full_tournament_details
from bracket.sql.tournaments import sql_get_tournament, sql_move_tournament_start
from bracket.utils.i18n import gettext
from bracket.utils.id_types import MatchId, TournamentId


def plan_match_timings(
    stages: list[StageWithStageItems],
    tournament: Tournament,
    *,
    lineups: Lineups | None = None,
    elsewhere: Calendar | None = None,
) -> list[MatchTiming]:
    """
    Plan when every match of the tournament starts.

    The rounds of a stage item follow each other: a round starts once every match of the previous
    round has finished, including its margin. The stage items of a stage are played in parallel,
    and a stage starts once every stage item of the previous stage has finished.

    The matches of a round start with the round, unless their teams, or the players of the
    `lineups`, play a match of another tournament then (`elsewhere`). Such a match waits until all
    of them are free.

    The tournament's match duration is a default that a stage can overwrite for its matches. The
    custom duration of a match takes precedence over both.
    """
    lineups = lineups if lineups is not None else Lineups({})
    elsewhere = elsewhere if elsewhere is not None else Calendar()
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
                round_end = round_start

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
                    start_time = elsewhere.earliest_start(
                        lineups.competitors(match), round_start, duration_minutes + margin_minutes
                    )
                    timings.append(
                        MatchTiming(
                            match_id=match.id,
                            start_time=start_time,
                            duration_minutes=duration_minutes,
                            margin_minutes=margin_minutes,
                        )
                    )
                    round_end = max(
                        round_end,
                        start_time + timedelta(minutes=duration_minutes + margin_minutes),
                    )

                round_start = round_end

            stage_end = max(stage_end, round_start)

        stage_start = stage_end

    return timings


async def schedule_all_matches(
    session: AsyncSession,
    tournament_id: TournamentId,
    *,
    graph: TournamentGraph | None = None,
    tournament: Tournament | None = None,
) -> None:
    """
    Update the start time of every match whose planned time has changed.

    Call this whenever rounds or matches are added or removed, or when the tournament's start
    time or any match duration or margin changes. A command that has the whole tournament's
    graph passes it, which also gets the new times.

    The matches of other tournaments stay where they are: this tournament's matches avoid them.
    """
    if tournament is None:
        tournament = await sql_get_tournament(session, tournament_id)
    if graph is None:
        graph = TournamentGraph(await get_full_tournament_details(session, tournament_id))
    lineups = Lineups(await get_lineups(session, tournament_id))
    elsewhere = Calendar.of_matches_elsewhere(await get_matches_elsewhere(session, tournament_id))

    changed_timings: list[MatchTiming] = []
    for timing in plan_match_timings(
        graph.stages, tournament, lineups=lineups, elsewhere=elsewhere
    ):
        match = graph.match(timing.match_id)
        if (match.start_time, match.duration_minutes, match.margin_minutes) != (
            timing.start_time,
            timing.duration_minutes,
            timing.margin_minutes,
        ):
            changed_timings.append(timing)
    await sql_update_match_timings(session, changed_timings)
    for timing in changed_timings:
        graph.update_match(
            timing.match_id,
            start_time=timing.start_time,
            duration_minutes=timing.duration_minutes,
            margin_minutes=timing.margin_minutes,
        )


class ScheduleDelay(NamedTuple):
    """How to move the rounds that are still to be played."""

    # The matches whose break grows, which moves every round after them.
    match_ids: list[MatchId]
    # Nothing has been played yet, so the tournament itself starts later.
    moves_tournament_start: bool


def _round_start(round_: RoundWithMatches) -> datetime_utc | None:
    return min(
        (match.start_time for match in round_.matches if match.start_time is not None),
        default=None,
    )


def plan_schedule_delay(stages: list[StageWithStageItems]) -> ScheduleDelay | None:
    """
    Work out what has to change so that every round that is still to come starts later.

    The schedule is derived: a round starts when the round before it ends, and a stage when the
    stage before it ends. So a round moves by lengthening the break after the round before it,
    and a stage by lengthening the break after the last rounds of the stage before it.

    The latest round, by planned time, in which a match has a result is the one being played,
    together with the rounds that other groups play at that time. They stay where they are, and
    so does everything before them. The delay starts at the first round planned after that.
    Returns `None` when no such round is left.
    """
    # Per stage, per stage item: its rounds that have matches, with the time they start.
    planned_stages = [
        [
            [
                (round_, start)
                for round_ in sorted(stage_item.rounds, key=lambda round_: round_.id)
                if (start := _round_start(round_)) is not None
            ]
            for stage_item in stage.stage_items
        ]
        for stage in sorted(stages, key=lambda stage: stage.id)
    ]
    planned_stages = [
        [rounds for rounds in stage_items if len(rounds) > 0] for stage_items in planned_stages
    ]
    planned_stages = [stage_items for stage_items in planned_stages if len(stage_items) > 0]

    planned_rounds = [
        (start, any(is_played(match) for match in round_.matches))
        for stage_items in planned_stages
        for rounds in stage_items
        for round_, start in rounds
    ]
    being_played = max((start for start, has_result in planned_rounds if has_result), default=None)
    delayed_from = min(
        (start for start, _ in planned_rounds if being_played is None or start > being_played),
        default=None,
    )
    if delayed_from is None:
        return None

    match_ids: list[MatchId] = []

    def lengthen_break_after(round_: RoundWithMatches) -> None:
        match_ids.extend(match.id for match in round_.matches)

    for index, stage_items in enumerate(planned_stages):
        stage_start = min(rounds[0][1] for rounds in stage_items)

        if stage_start >= delayed_from:
            # The whole stage moves, and with it every stage after it.
            if index == 0:
                return ScheduleDelay(match_ids=[], moves_tournament_start=True)

            for rounds in planned_stages[index - 1]:
                # Stage items that already had a round moved end later by themselves.
                if all(start < delayed_from for _, start in rounds):
                    lengthen_break_after(rounds[-1][0])
            break

        for rounds in stage_items:
            first_delayed = next(
                (position for position, (_, start) in enumerate(rounds) if start >= delayed_from),
                None,
            )
            if first_delayed is not None and first_delayed > 0:
                lengthen_break_after(rounds[first_delayed - 1][0])

    return ScheduleDelay(match_ids=match_ids, moves_tournament_start=False)


async def delay_upcoming_matches(
    session: AsyncSession, tournament_id: TournamentId, minutes: int
) -> None:
    """Move the rounds that are still to be played, for an event that runs late (or early)."""
    tournament = await sql_get_tournament(session, tournament_id)
    stages = await get_full_tournament_details(session, tournament_id)
    delay = plan_schedule_delay(stages)
    if delay is None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=gettext("Every round has started already, so there is nothing left to move"),
        )

    if delay.moves_tournament_start:
        await sql_move_tournament_start(session, tournament_id, minutes)
    else:
        affected = set(delay.match_ids)
        margins = [
            match.custom_margin_minutes
            if match.custom_margin_minutes is not None
            else tournament.margin_minutes
            for stage in stages
            for stage_item in stage.stage_items
            for round_ in stage_item.rounds
            for match in round_.matches
            if match.id in affected
        ]
        if minutes > MAX_MINUTES - max(margins):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=gettext(
                    "The remaining rounds can move later by at most {available} minutes without "
                    "exceeding the maximum break of {maximum} minutes.",
                    available=MAX_MINUTES - max(margins),
                    maximum=MAX_MINUTES,
                ),
            )
        if minutes < 0:
            available_break = min(margins)
            if -minutes > available_break:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=gettext(
                        "The remaining rounds can move earlier by at most {available} minutes "
                        "without overlapping the previous round.",
                        available=available_break,
                    ),
                )
        await sql_add_margin_to_matches(
            session, delay.match_ids, tournament.margin_minutes, minutes
        )

    await schedule_all_matches(session, tournament_id)
