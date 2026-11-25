"""
How teams and players take part in tournaments.

A team takes part in a tournament through a participation (`tournament_teams`). The tournament's
lineup (`tournament_players`) says which team each of its players plays for. The lineups of open
tournaments follow the active members of their teams, so whatever changes a roster or a
tournament's teams brings them up to date with `sync_lineups`. Archived tournaments keep theirs as
they were.
"""

from collections import defaultdict
from collections.abc import Collection, Mapping
from dataclasses import dataclass
from typing import Any, NamedTuple, Self

from sqlalchemy import (
    ColumnElement,
    Select,
    and_,
    delete,
    exists,
    func,
    insert,
    select,
    union,
    update,
)
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import InstrumentedAttribute, joinedload, selectinload

from bracket import orm
from bracket.models.db.participation import (
    TournamentPlayer,
    TournamentTeam,
    TournamentTeamWithPlayers,
)
from bracket.models.db.player import Player
from bracket.models.enums import TournamentStatus
from bracket.utils.id_types import PlayerId, TeamId, TournamentId
from bracket.utils.pagination import PlayerPagination, TeamPagination

STORED_TEAM_SORT_COLUMNS: Mapping[str, InstrumentedAttribute[Any]] = {
    "name": orm.Team.name,
    "active": orm.TournamentTeam.active,
    "created": orm.Team.created,
}
STORED_PLAYER_SORT_COLUMNS: Mapping[str, InstrumentedAttribute[Any]] = {
    "name": orm.Player.name,
    "created": orm.Player.created,
}


async def get_tournament_teams(
    session: AsyncSession,
    tournament_id: TournamentId,
    *,
    team_id: TeamId | None = None,
    pagination: TeamPagination | None = None,
) -> list[TournamentTeamWithPlayers]:
    """
    The teams that take part, with their lineups, by name. With `pagination` that sorts by a stored
    field, only that page in that order.
    """
    query = (
        select(orm.TournamentTeam)
        .join(orm.Team, orm.Team.id == orm.TournamentTeam.team_id)
        .where(orm.TournamentTeam.tournament_id == tournament_id)
        .options(joinedload(orm.TournamentTeam.team), selectinload(orm.TournamentTeam.players))
        .execution_options(populate_existing=True)
    )
    if team_id is not None:
        query = query.where(orm.TournamentTeam.team_id == team_id)
    if pagination is not None and pagination.sorts_by_results:
        raise ValueError("Results aren't stored: sorting by them happens in bracket.logic")
    if pagination is not None:
        sort_column = STORED_TEAM_SORT_COLUMNS[pagination.sort_by]
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
    return [
        TournamentTeamWithPlayers.model_validate(entity) for entity in await session.scalars(query)
    ]


async def get_tournament_team(
    session: AsyncSession, tournament_id: TournamentId, team_id: TeamId
) -> TournamentTeam | None:
    entity = await session.scalar(
        select(orm.TournamentTeam)
        .where(
            orm.TournamentTeam.tournament_id == tournament_id,
            orm.TournamentTeam.team_id == team_id,
        )
        .options(joinedload(orm.TournamentTeam.team))
        .execution_options(populate_existing=True)
    )
    return TournamentTeam.model_validate(entity) if entity is not None else None


async def get_participating_team_ids(
    session: AsyncSession, tournament_id: TournamentId
) -> set[TeamId]:
    return {
        TeamId(team_id)
        for team_id in await session.scalars(
            select(orm.TournamentTeam.team_id).where(
                orm.TournamentTeam.tournament_id == tournament_id
            )
        )
    }


async def get_open_tournament_ids(session: AsyncSession, team_id: TeamId) -> list[TournamentId]:
    """The open tournaments the team takes part in, by id: the order their locks are taken in."""
    return [
        TournamentId(tournament_id)
        for tournament_id in await session.scalars(
            select(orm.TournamentTeam.tournament_id)
            .join(orm.Tournament, orm.Tournament.id == orm.TournamentTeam.tournament_id)
            .where(
                orm.TournamentTeam.team_id == team_id,
                orm.Tournament.status == TournamentStatus.OPEN,
            )
            .order_by(orm.TournamentTeam.tournament_id)
        )
    ]


async def get_tournament_players(
    session: AsyncSession,
    tournament_id: TournamentId,
    *,
    pagination: PlayerPagination | None = None,
) -> list[TournamentPlayer]:
    """
    The tournament's lineup: its players with the teams they play for, by name. With `pagination`
    that sorts by a stored field, only that page in that order.
    """
    query = (
        select(orm.Player, orm.TournamentPlayer.team_id)
        .join(orm.TournamentPlayer, orm.TournamentPlayer.player_id == orm.Player.id)
        .where(orm.TournamentPlayer.tournament_id == tournament_id)
        .execution_options(populate_existing=True)
    )
    if pagination is not None and pagination.sorts_by_results:
        raise ValueError("Results aren't stored: sorting by them happens in bracket.logic")
    if pagination is not None:
        sort_column = STORED_PLAYER_SORT_COLUMNS[pagination.sort_by]
        query = (
            query.order_by(
                sort_column.desc() if pagination.sort_direction == "desc" else sort_column.asc(),
                orm.Player.id,
            )
            .limit(pagination.limit)
            .offset(pagination.offset)
        )
    else:
        query = query.order_by(orm.Player.name, orm.Player.id)
    return [
        TournamentPlayer(**Player.model_validate(player).model_dump(), team_id=TeamId(team_id))
        for player, team_id in await session.execute(query)
    ]


async def get_lineups(
    session: AsyncSession, tournament_id: TournamentId
) -> dict[TeamId, frozenset[PlayerId]]:
    """The players each team of the tournament plays with there."""
    lineups: defaultdict[TeamId, set[PlayerId]] = defaultdict(set)
    rows = await session.execute(
        select(orm.TournamentPlayer.team_id, orm.TournamentPlayer.player_id).where(
            orm.TournamentPlayer.tournament_id == tournament_id
        )
    )
    for team_id, player_id in rows:
        lineups[TeamId(team_id)].add(PlayerId(player_id))
    return {team_id: frozenset(player_ids) for team_id, player_ids in lineups.items()}


async def sql_add_tournament_teams(
    session: AsyncSession, tournament_id: TournamentId, team_ids: Collection[TeamId]
) -> None:
    session.add_all(
        orm.TournamentTeam(tournament_id=tournament_id, team_id=team_id, active=True)
        for team_id in sorted(team_ids)
    )
    await session.flush()


async def sql_set_tournament_team_active(
    session: AsyncSession, tournament_id: TournamentId, team_id: TeamId, active: bool
) -> None:
    await session.execute(
        update(orm.TournamentTeam)
        .where(
            orm.TournamentTeam.tournament_id == tournament_id,
            orm.TournamentTeam.team_id == team_id,
        )
        .values(active=active)
    )


async def sql_remove_tournament_team(
    session: AsyncSession, tournament_id: TournamentId, team_id: TeamId
) -> None:
    """The team leaves the tournament, and its players the tournament's lineup."""
    await session.execute(
        delete(orm.TournamentTeam).where(
            orm.TournamentTeam.tournament_id == tournament_id,
            orm.TournamentTeam.team_id == team_id,
        )
    )


@dataclass(frozen=True)
class LineupScope:
    """
    The participations whose lineups are brought up to date: those of some teams in their
    tournaments, or those of every team of one tournament. Only open tournaments count.
    """

    team_ids: frozenset[TeamId] | None = None
    tournament_id: TournamentId | None = None

    @classmethod
    def of_teams(cls, team_ids: Collection[TeamId]) -> Self:
        return cls(team_ids=frozenset(team_ids))

    @classmethod
    def of_tournament(cls, tournament_id: TournamentId) -> Self:
        return cls(tournament_id=tournament_id)

    def covers(
        self,
        tournament_id: ColumnElement[int] | InstrumentedAttribute[int],
        team_id: ColumnElement[int] | InstrumentedAttribute[int],
    ) -> ColumnElement[bool]:
        """Whether the scope covers the participation with these columns."""
        if self.team_ids is not None:
            return team_id.in_(self.team_ids)
        return tournament_id == self.tournament_id

    def open_participations(self) -> Select[int, int]:
        """The participations the scope covers, in open tournaments."""
        return (
            select(orm.TournamentTeam.tournament_id, orm.TournamentTeam.team_id)
            .join(orm.Tournament, orm.Tournament.id == orm.TournamentTeam.tournament_id)
            .where(
                orm.Tournament.status == TournamentStatus.OPEN,
                self.covers(orm.TournamentTeam.tournament_id, orm.TournamentTeam.team_id),
            )
        )


def _desired_lineups(scope: LineupScope) -> Select[int, int, int]:
    """The lineup rows the scope's participations should have: their teams' active members."""
    participations = scope.open_participations().subquery()
    return select(
        participations.c.tournament_id,
        orm.TeamMember.player_id,
        participations.c.team_id,
    ).join(
        orm.TeamMember,
        and_(orm.TeamMember.team_id == participations.c.team_id, orm.TeamMember.active),
    )


class LineupClash(NamedTuple):
    """A player who would play for two teams in one tournament."""

    tournament_name: str
    player_name: str
    team_names: tuple[str, str]


async def find_lineup_clash(session: AsyncSession, scope: LineupScope) -> LineupClash | None:
    """
    A player who would play for two teams in a tournament once the scope's lineups follow their
    rosters, together with the lineups of other teams that stay as they are.
    """
    desired = _desired_lineups(scope).cte("desired")
    lineup = orm.TournamentPlayer
    kept = select(lineup.tournament_id, lineup.player_id, lineup.team_id).where(
        lineup.tournament_id.in_(select(desired.c.tournament_id)),
        ~scope.covers(lineup.tournament_id, lineup.team_id),
    )
    rows = union(select(desired), kept).subquery()
    clash = (
        await session.execute(
            select(
                rows.c.tournament_id,
                rows.c.player_id,
                func.min(rows.c.team_id),
                func.max(rows.c.team_id),
            )
            .group_by(rows.c.tournament_id, rows.c.player_id)
            .having(func.count(rows.c.team_id.distinct()) > 1)
            .order_by(rows.c.tournament_id, rows.c.player_id)
            .limit(1)
        )
    ).first()
    if clash is None:
        return None

    tournament_id, player_id, team1_id, team2_id = clash
    names = (
        await session.execute(
            select(
                select(orm.Tournament.name)
                .where(orm.Tournament.id == tournament_id)
                .scalar_subquery(),
                select(orm.Player.name).where(orm.Player.id == player_id).scalar_subquery(),
                select(orm.Team.name).where(orm.Team.id == team1_id).scalar_subquery(),
                select(orm.Team.name).where(orm.Team.id == team2_id).scalar_subquery(),
            )
        )
    ).one()
    tournament_name, player_name, team1_name, team2_name = names
    first, second = sorted((team1_name, team2_name))
    return LineupClash(tournament_name, player_name, (first, second))


async def sync_lineups(session: AsyncSession, scope: LineupScope) -> None:
    """
    Make the scope's lineups follow their teams' active members. A player who would play for two
    teams in a tournament violates the primary key of `tournament_players`; check
    `find_lineup_clash` first to say who.
    """
    lineup = orm.TournamentPlayer
    covered = scope.open_participations().subquery()
    await session.execute(
        delete(lineup)
        .where(
            exists().where(
                covered.c.tournament_id == lineup.tournament_id,
                covered.c.team_id == lineup.team_id,
            ),
            ~exists().where(
                orm.TeamMember.team_id == lineup.team_id,
                orm.TeamMember.player_id == lineup.player_id,
                orm.TeamMember.active,
            ),
        )
        .execution_options(synchronize_session=False)
    )

    desired = _desired_lineups(scope).subquery()
    await session.execute(
        insert(lineup).from_select(
            ["tournament_id", "player_id", "team_id"],
            select(desired.c.tournament_id, desired.c.player_id, desired.c.team_id)
            .where(
                ~exists().where(
                    lineup.tournament_id == desired.c.tournament_id,
                    lineup.player_id == desired.c.player_id,
                    lineup.team_id == desired.c.team_id,
                )
            )
            .order_by(desired.c.tournament_id, desired.c.player_id),
        )
    )
