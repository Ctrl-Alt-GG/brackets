"""The matches whose teams, or players of them, have to be somewhere else at the same time."""

from sqlalchemy.ext.asyncio import AsyncSession
from starlette.concurrency import run_in_threadpool

from bracket.logic.planning.calendar import Booking, Calendar, Lineups
from bracket.models.db.stage_tree import StageWithStageItems
from bracket.models.db.tournament import Tournament
from bracket.models.schedule import ScheduleConflict
from bracket.sql.matches import get_matches_elsewhere
from bracket.sql.participation import get_lineups


def find_conflicts(
    tournament: Tournament,
    stages: list[StageWithStageItems],
    lineups: Lineups,
    elsewhere: Calendar,
) -> list[ScheduleConflict]:
    """
    Every match of the tournament whose team plays another match at the same time, in this
    tournament or in another one, or whose players play one for another team. A match takes its
    teams until its break ends. A match without a time doesn't clash.

    Within the tournament, a player plays for one team, so comparing its matches by team also
    covers the players.
    """
    timed_matches = [
        (match, match.start_time)
        for stage in stages
        for stage_item in stage.stage_items
        for round_ in stage_item.rounds
        for match in round_.matches
        if match.start_time is not None
    ]
    here = Calendar()
    for match, start in timed_matches:
        booking = Booking(
            match_id=match.id,
            tournament_id=tournament.id,
            tournament_name=tournament.name,
            start=start,
            end=match.end_time,
        )
        for side in lineups.competitors(match):
            here.book_team(side.team_id, booking)

    conflicts: list[ScheduleConflict] = []
    for match, start in timed_matches:
        for side in lineups.competitors(match):
            for calendar in (here, elsewhere):
                conflicts.extend(
                    ScheduleConflict(
                        match_id=match.id,
                        team_id=side.team_id,
                        player_ids=sorted(clash.player_ids),
                        other_match_id=clash.booking.match_id,
                        other_tournament_id=clash.booking.tournament_id,
                        other_tournament_name=clash.booking.tournament_name,
                    )
                    for clash in calendar.clashes(side, start, match.end_time, excluding=match.id)
                )
    return conflicts


async def get_schedule_conflicts(
    session: AsyncSession, tournament: Tournament, stages: list[StageWithStageItems]
) -> list[ScheduleConflict]:
    lineups = Lineups(await get_lineups(session, tournament.id))
    elsewhere = Calendar.of_matches_elsewhere(await get_matches_elsewhere(session, tournament.id))
    # Comparing every match of a big tournament takes a while. In a worker thread, other requests
    # are still answered meanwhile.
    return await run_in_threadpool(find_conflicts, tournament, stages, lineups, elsewhere)
