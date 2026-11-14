from heliclockter import datetime_utc
from sqlalchemy import delete, func, select, update
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from bracket import orm
from bracket.logic.ranking.statistics import START_ELO, TeamStatistics, TeamTotals
from bracket.logic.ranking.team_totals import get_team_totals
from bracket.models.db.team import FullTeamWithPlayers, Team, TeamBody
from bracket.utils.id_types import PlayerId, StageItemInputId, TeamId, TournamentId
from bracket.utils.pagination import PaginationTeams


async def get_teams_by_id(
    conn: AsyncSession,
    team_ids: set[TeamId],
    tournament_id: TournamentId,
    *,
    with_totals: bool = False,
) -> list[Team]:
    """
    `with_totals` fills in the teams' results, which replays every match of the tournament. Only
    answers that show the teams need it: without it, they carry the never-updated result columns.
    """
    if not team_ids:
        return []
    entities = await conn.scalars(
        select(orm.Team)
        .where(orm.Team.id.in_(team_ids), orm.Team.tournament_id == tournament_id)
        .execution_options(populate_existing=True)
    )
    teams = [Team.model_validate(entity) for entity in entities]
    if not teams or not with_totals:
        return teams
    totals = await get_team_totals(conn, tournament_id)
    return [
        team.model_copy(update=totals.get(team.id, TeamTotals()).model_dump()) for team in teams
    ]


async def get_team_by_id(
    conn: AsyncSession,
    team_id: TeamId,
    tournament_id: TournamentId,
    *,
    with_totals: bool = False,
) -> Team | None:
    result = await get_teams_by_id(conn, {team_id}, tournament_id, with_totals=with_totals)
    return result[0] if result else None


async def get_teams_with_members(
    conn: AsyncSession,
    tournament_id: TournamentId,
    *,
    only_active_teams: bool = False,
    team_id: TeamId | None = None,
    pagination: PaginationTeams | None = None,
) -> list[FullTeamWithPlayers]:
    totals_sort = pagination is None or pagination.sort_by in TeamTotals.model_fields
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
    if pagination is not None and not totals_sort:
        sort_columns = {
            "name": orm.Team.name,
            "active": orm.Team.active,
            "created": orm.Team.created,
        }
        sort_column = sort_columns[pagination.sort_by]
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
    entities = (await conn.scalars(query)).all()
    if not entities:
        return []
    totals = await get_team_totals(conn, tournament_id)
    teams = [
        FullTeamWithPlayers.model_validate(entity).model_copy(
            update=totals.get(TeamId(entity.id), TeamTotals()).model_dump()
        )
        for entity in entities
    ]
    if pagination is None:
        teams.sort(key=lambda team: (-team.elo_score, -team.wins, team.name, team.id))
    elif totals_sort:
        teams.sort(
            key=lambda team: getattr(team, pagination.sort_by),
            reverse=pagination.sort_direction == "desc",
        )
        teams = teams[pagination.offset : pagination.offset + pagination.limit]
    return teams


async def get_team_count(
    conn: AsyncSession,
    tournament_id: TournamentId,
    *,
    only_active_teams: bool = False,
) -> int:
    query = (
        select(func.count()).select_from(orm.Team).where(orm.Team.tournament_id == tournament_id)
    )
    if only_active_teams:
        query = query.where(orm.Team.active.is_(True))
    return int(await conn.scalar(query) or 0)


async def update_stage_item_input_statistics(
    conn: AsyncSession,
    tournament_id: TournamentId,
    statistics: dict[StageItemInputId, TeamStatistics],
) -> None:
    """Store the results of these slots, in one round trip to the database."""
    if not statistics:
        return
    await conn.execute(
        update(orm.StageItemInput)
        .where(orm.StageItemInput.tournament_id == tournament_id)
        .execution_options(synchronize_session=False),
        [
            {
                "id": stage_item_input_id,
                "wins": input_statistics.wins,
                "draws": input_statistics.draws,
                "losses": input_statistics.losses,
                "points": float(input_statistics.points),
            }
            for stage_item_input_id, input_statistics in statistics.items()
        ],
    )


async def sql_create_team(
    conn: AsyncSession, tournament_id: TournamentId, name: str, active: bool
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
    conn.add(entity)
    await conn.flush()
    return TeamId(entity.id)


async def sql_update_team(
    conn: AsyncSession, tournament_id: TournamentId, team_id: TeamId, body: TeamBody
) -> None:
    entity = await conn.scalar(
        select(orm.Team).where(orm.Team.id == team_id, orm.Team.tournament_id == tournament_id)
    )
    if entity is not None:
        entity.name = body.name
        entity.active = body.active
        await conn.flush()


async def sql_update_team_logo(conn: AsyncSession, team_id: TeamId, logo_path: str | None) -> None:
    entity = await conn.get(orm.Team, team_id)
    if entity is not None:
        entity.logo_path = logo_path
        await conn.flush()


async def sql_add_team_player(conn: AsyncSession, team_id: TeamId, player_id: PlayerId) -> None:
    conn.add(orm.PlayerXTeam(team_id=team_id, player_id=player_id))
    await conn.flush()


async def sql_set_team_members(
    conn: AsyncSession, team_id: TeamId, player_ids: set[PlayerId], previous_ids: set[PlayerId]
) -> None:
    conn.add_all(
        orm.PlayerXTeam(team_id=team_id, player_id=player_id)
        for player_id in player_ids - previous_ids
    )
    await conn.flush()
    await conn.execute(
        delete(orm.PlayerXTeam).where(
            orm.PlayerXTeam.player_id.not_in(player_ids), orm.PlayerXTeam.team_id == team_id
        )
    )


async def sql_delete_team(conn: AsyncSession, tournament_id: TournamentId, team_id: TeamId) -> None:
    await conn.execute(
        delete(orm.Team).where(orm.Team.id == team_id, orm.Team.tournament_id == tournament_id)
    )


async def sql_delete_teams_of_tournament(conn: AsyncSession, tournament_id: TournamentId) -> None:
    await conn.execute(delete(orm.Team).where(orm.Team.tournament_id == tournament_id))
