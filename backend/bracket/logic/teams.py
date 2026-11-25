"""
Teams and their rosters. Teams are shared by every tournament.

A roster change reaches the team's open tournaments: their lineups follow it, and their schedules
are planned again, as a player who joins can play elsewhere at the planned times. Archived
tournaments keep their lineups. Such a command locks the team, then its open tournaments by id
(`bracket.logic.participation` explains why that order can't deadlock).
"""

from fastapi import HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from starlette import status

from bracket.logic.participation import follow_rosters
from bracket.logic.planning.matches import schedule_all_matches
from bracket.logic.subscriptions import Limit, check_requirement
from bracket.models.db.team import TeamBody, TeamWithMembers
from bracket.models.db.user import UserPublic
from bracket.sql.participation import LineupScope, get_open_tournament_ids
from bracket.sql.teams import (
    get_teams_with_members,
    lock_team,
    sql_create_team,
    sql_delete_team,
    sql_rename_team,
    sql_replace_team_members,
)
from bracket.sql.tournaments import lock_tournament
from bracket.sql.validation import validate_player_ids
from bracket.utils.errors import ForeignKey, check_foreign_key_violation
from bracket.utils.i18n import gettext
from bracket.utils.id_types import TeamId


def _team_not_found(team_id: TeamId) -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_404_NOT_FOUND,
        detail=gettext("Could not find team with id {id}", id=team_id),
    )


async def get_team_with_members(session: AsyncSession, team_id: TeamId) -> TeamWithMembers:
    teams = await get_teams_with_members(session, team_id)
    if not teams:
        raise _team_not_found(team_id)
    return teams[0]


async def _check_roster(session: AsyncSession, body: TeamBody, user: UserPublic) -> None:
    check_requirement(Limit.PLAYERS, 0, user, additions=len(body.members))
    await validate_player_ids(session, {member.player_id for member in body.members})


async def create_team(session: AsyncSession, body: TeamBody, user: UserPublic) -> TeamWithMembers:
    """A new team takes part in no tournament yet, so its roster reaches no lineup."""
    await _check_roster(session, body, user)
    team_id = await sql_create_team(session, body.name)
    await sql_replace_team_members(session, team_id, body.members)
    return await get_team_with_members(session, team_id)


async def update_team(
    session: AsyncSession, team_id: TeamId, body: TeamBody, user: UserPublic
) -> TeamWithMembers:
    """Rename the team and replace its roster."""
    await _check_roster(session, body, user)
    if not await lock_team(session, team_id):
        raise _team_not_found(team_id)
    # One deleted before its lock is taken has no lineup left to follow the roster.
    tournament_ids = [
        tournament_id
        for tournament_id in await get_open_tournament_ids(session, team_id)
        if await lock_tournament(session, tournament_id)
    ]

    await sql_rename_team(session, team_id, body.name)
    await sql_replace_team_members(session, team_id, body.members)
    await follow_rosters(session, LineupScope.of_teams({team_id}))
    for tournament_id in tournament_ids:
        await schedule_all_matches(session, tournament_id)
    return await get_team_with_members(session, team_id)


async def delete_team(session: AsyncSession, team_id: TeamId) -> None:
    """Delete a team that takes part in no tournament, with its roster."""
    team = await get_team_with_members(session, team_id)
    if team.participations:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=gettext(
                "{team} takes part in {tournaments}. Remove it from those tournaments first.",
                team=team.name,
                tournaments=", ".join(
                    participation.tournament_name for participation in team.participations
                ),
            ),
        )
    # It can join a tournament in the meantime.
    with check_foreign_key_violation({ForeignKey.tournament_teams_team_id_fkey}):
        await sql_delete_team(session, team.id)
