"""
Teams and their rosters as they are stored. They are shared by every tournament.

The teams of one tournament, with their results there, are in `bracket.sql.participation`. A
roster change has to reach the lineups of the team's tournaments: see `bracket.logic.teams`.
"""

from collections.abc import Collection, Sequence

from heliclockter import datetime_utc
from sqlalchemy import delete, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from bracket import orm
from bracket.models.db.team import Team, TeamMemberBody, TeamWithMembers
from bracket.utils.id_types import PlayerId, TeamId


async def lock_team(session: AsyncSession, team_id: TeamId) -> bool:
    """
    Serialize the commands that change a team, so that two roster changes can't interleave.
    `False` when it doesn't exist.

    A team that joins a tournament meanwhile doesn't wait for it. The rule that a player plays for
    one team per tournament holds anyway: the primary key of `tournament_players` enforces it.
    """
    return (
        await session.scalar(
            select(orm.Team.id).where(orm.Team.id == team_id).with_for_update(key_share=True)
        )
    ) is not None


async def get_existing_team_ids(session: AsyncSession, team_ids: Collection[TeamId]) -> set[TeamId]:
    """Those of these teams that exist."""
    if not team_ids:
        return set()
    return {
        TeamId(team_id)
        for team_id in await session.scalars(select(orm.Team.id).where(orm.Team.id.in_(team_ids)))
    }


async def lock_teams_against_changes(session: AsyncSession, team_ids: Collection[TeamId]) -> None:
    """
    Wait for the commands that change these teams, and keep them from changing until this command
    ends. A command that makes a tournament's lineups follow its teams' rosters takes it, after
    the tournament's lock, so that the rosters it reads stay as they are.
    """
    if team_ids:
        await session.execute(
            select(orm.Team.id)
            .where(orm.Team.id.in_(team_ids))
            .order_by(orm.Team.id)
            .with_for_update(read=True)
        )


async def get_team(session: AsyncSession, team_id: TeamId) -> Team | None:
    entity = await session.get(orm.Team, team_id, populate_existing=True)
    return Team.model_validate(entity) if entity is not None else None


async def get_teams_with_members(
    session: AsyncSession, team_id: TeamId | None = None
) -> list[TeamWithMembers]:
    """Every team, or the one with `team_id`, by name: their rosters and their tournaments."""
    query = (
        select(orm.Team)
        .options(
            selectinload(orm.Team.members).joinedload(orm.TeamMember.player),
            selectinload(orm.Team.participations).joinedload(orm.TournamentTeam.tournament),
        )
        .order_by(orm.Team.name, orm.Team.id)
        .execution_options(populate_existing=True)
    )
    if team_id is not None:
        query = query.where(orm.Team.id == team_id)
    teams = [TeamWithMembers.model_validate(entity) for entity in await session.scalars(query)]
    for team in teams:
        team.members.sort(key=lambda member: (member.player.name, member.player.id))
    return teams


async def sql_create_team(session: AsyncSession, name: str) -> TeamId:
    entity = orm.Team(name=name, created=datetime_utc.now())
    session.add(entity)
    await session.flush()
    return TeamId(entity.id)


async def sql_rename_team(session: AsyncSession, team_id: TeamId, name: str) -> None:
    entity = await session.get(orm.Team, team_id)
    if entity is not None:
        entity.name = name
        await session.flush()


async def sql_update_team_logo(
    session: AsyncSession, team_id: TeamId, logo_path: str | None
) -> None:
    entity = await session.get(orm.Team, team_id)
    if entity is not None:
        entity.logo_path = logo_path
        await session.flush()


async def sql_add_team_members(
    session: AsyncSession, team_id: TeamId, player_ids: Sequence[PlayerId]
) -> None:
    """Add these players to the team's roster as active members."""
    session.add_all(
        orm.TeamMember(team_id=team_id, player_id=player_id, active=True)
        for player_id in player_ids
    )
    await session.flush()


async def sql_replace_team_members(
    session: AsyncSession, team_id: TeamId, members: Sequence[TeamMemberBody]
) -> None:
    """Make these the team's roster, and set whether each of them is active."""
    await session.execute(
        delete(orm.TeamMember).where(
            orm.TeamMember.team_id == team_id,
            orm.TeamMember.player_id.not_in([member.player_id for member in members]),
        )
    )
    if members:
        statement = insert(orm.TeamMember).values(
            [
                {"team_id": team_id, "player_id": member.player_id, "active": member.active}
                for member in sorted(members, key=lambda member: member.player_id)
            ]
        )
        await session.execute(
            statement.on_conflict_do_update(
                index_elements=[orm.TeamMember.team_id, orm.TeamMember.player_id],
                set_={"active": statement.excluded.active},
            )
        )


async def sql_delete_team(session: AsyncSession, team_id: TeamId) -> None:
    """Delete the team with its roster. One that takes part in a tournament can't be deleted."""
    await session.execute(delete(orm.Team).where(orm.Team.id == team_id))
