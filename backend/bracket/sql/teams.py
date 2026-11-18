"""
Teams as they are stored.

Their results are worked out from the matches instead: see `bracket.logic.teams`, which also owns
sorting by results.
"""

from collections.abc import Mapping
from typing import Any

from heliclockter import datetime_utc
from sqlalchemy import delete, func, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import InstrumentedAttribute, selectinload

from bracket import orm
from bracket.models.db.player import Player
from bracket.models.db.team import FullTeamWithPlayers, Team, TeamBody
from bracket.models.results import START_ELO
from bracket.utils.id_types import PlayerId, TeamId, TournamentId
from bracket.utils.pagination import ParticipantPagination

STORED_SORT_COLUMNS: Mapping[str, InstrumentedAttribute[Any]] = {
    "name": orm.Team.name,
    "active": orm.Team.active,
    "created": orm.Team.created,
}


async def get_teams_by_id(
    session: AsyncSession, team_ids: set[TeamId], tournament_id: TournamentId
) -> list[Team]:
    if not team_ids:
        return []
    entities = await session.scalars(
        select(orm.Team)
        .where(orm.Team.id.in_(team_ids), orm.Team.tournament_id == tournament_id)
        .execution_options(populate_existing=True)
    )
    return [Team.model_validate(entity) for entity in entities]


async def get_team_by_id(
    session: AsyncSession, team_id: TeamId, tournament_id: TournamentId
) -> Team | None:
    result = await get_teams_by_id(session, {team_id}, tournament_id)
    return result[0] if result else None


async def get_teams_with_members(
    session: AsyncSession,
    tournament_id: TournamentId,
    *,
    only_active_teams: bool = False,
    team_id: TeamId | None = None,
    pagination: ParticipantPagination | None = None,
) -> list[FullTeamWithPlayers]:
    """
    The teams with their players, by name. With `pagination` that sorts by a stored field, only
    that page in that order.
    """
    query = (
        select(orm.Team)
        .where(orm.Team.tournament_id == tournament_id)
        .options(selectinload(orm.Team.players))
        .execution_options(populate_existing=True)
    )
    if only_active_teams:
        query = query.where(orm.Team.active.is_(True))
    if team_id is not None:
        query = query.where(orm.Team.id == team_id)
    if pagination is not None and pagination.sorts_by_results:
        raise ValueError("Results aren't stored: sorting by them happens in bracket.logic")
    if pagination is not None:
        sort_column = STORED_SORT_COLUMNS[pagination.sort_by]
        query = (
            query.order_by(
                sort_column.desc() if pagination.sort_direction == "desc" else sort_column.asc(),
                orm.Team.id,
            )
            .limit(pagination.limit)
            .offset(pagination.offset)
        )
    else:
        query = query.order_by(orm.Team.name, orm.Team.id)
    return [FullTeamWithPlayers.model_validate(entity) for entity in await session.scalars(query)]


async def get_team_count(
    session: AsyncSession,
    tournament_id: TournamentId,
    *,
    only_active_teams: bool = False,
) -> int:
    query = (
        select(func.count()).select_from(orm.Team).where(orm.Team.tournament_id == tournament_id)
    )
    if only_active_teams:
        query = query.where(orm.Team.active.is_(True))
    return int(await session.scalar(query) or 0)


async def sql_create_team(
    session: AsyncSession, tournament_id: TournamentId, name: str, active: bool
) -> TeamId:
    entity = orm.Team(
        name=name,
        active=active,
        created=datetime_utc.now(),
        tournament_id=tournament_id,
        elo_score=float(START_ELO),
        swiss_score=0.0,
        wins=0,
        draws=0,
        losses=0,
    )
    session.add(entity)
    await session.flush()
    return TeamId(entity.id)


async def sql_update_team(
    session: AsyncSession, tournament_id: TournamentId, team_id: TeamId, body: TeamBody
) -> None:
    entity = await session.scalar(
        select(orm.Team).where(orm.Team.id == team_id, orm.Team.tournament_id == tournament_id)
    )
    if entity is not None:
        entity.name = body.name
        entity.active = body.active
        await session.flush()


async def sql_update_team_logo(
    session: AsyncSession, team_id: TeamId, logo_path: str | None
) -> None:
    entity = await session.get(orm.Team, team_id)
    if entity is not None:
        entity.logo_path = logo_path
        await session.flush()


async def sql_add_team_players(
    session: AsyncSession,
    tournament_id: TournamentId,
    team_id: TeamId,
    player_ids: list[PlayerId],
) -> None:
    session.add_all(
        orm.PlayerXTeam(tournament_id=tournament_id, team_id=team_id, player_id=player_id)
        for player_id in player_ids
    )
    await session.flush()


async def sql_replace_team_members(
    session: AsyncSession,
    tournament_id: TournamentId,
    team_id: TeamId,
    player_ids: set[PlayerId],
) -> None:
    """
    Make these players the team's members. Both changes are limited to the tournament: a team of
    another one keeps its members, and players of another one can't join.
    """
    await session.execute(
        delete(orm.PlayerXTeam).where(
            orm.PlayerXTeam.tournament_id == tournament_id,
            orm.PlayerXTeam.team_id == team_id,
            orm.PlayerXTeam.player_id.not_in(player_ids),
        )
    )
    if player_ids:
        await session.execute(
            insert(orm.PlayerXTeam)
            .values(
                [
                    {"tournament_id": tournament_id, "team_id": team_id, "player_id": player_id}
                    for player_id in sorted(player_ids)
                ]
            )
            .on_conflict_do_nothing(
                index_elements=[orm.PlayerXTeam.team_id, orm.PlayerXTeam.player_id]
            )
        )


async def sql_delete_team(
    session: AsyncSession, tournament_id: TournamentId, team_id: TeamId
) -> None:
    await session.execute(
        delete(orm.Team).where(orm.Team.id == team_id, orm.Team.tournament_id == tournament_id)
    )


async def get_team_player_ids(
    session: AsyncSession, tournament_id: TournamentId, team_id: TeamId
) -> set[PlayerId]:
    return {
        PlayerId(id_)
        for id_ in await session.scalars(
            select(orm.PlayerXTeam.player_id).where(
                orm.PlayerXTeam.tournament_id == tournament_id,
                orm.PlayerXTeam.team_id == team_id,
            )
        )
    }


async def find_player_in_other_team(
    session: AsyncSession,
    tournament_id: TournamentId,
    team_id: TeamId,
    player_ids: set[PlayerId],
) -> tuple[Player, str] | None:
    if not player_ids:
        return None
    result = await session.execute(
        select(orm.Player, orm.Team.name)
        .join(orm.PlayerXTeam, orm.PlayerXTeam.player_id == orm.Player.id)
        .join(orm.Team, orm.Team.id == orm.PlayerXTeam.team_id)
        .where(
            orm.Player.tournament_id == tournament_id,
            orm.PlayerXTeam.tournament_id == tournament_id,
            orm.PlayerXTeam.team_id != team_id,
            orm.Player.id.in_(player_ids),
        )
        .order_by(orm.Player.name, orm.Player.id)
        .limit(1)
    )
    row = result.first()
    return (Player.model_validate(row[0]), row[1]) if row is not None else None
