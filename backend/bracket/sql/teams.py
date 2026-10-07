from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncConnection

from bracket.logic.ranking.statistics import TeamStatistics
from bracket.models.db.team import FullTeamWithPlayers, Team
from bracket.utils.id_types import StageItemInputId, TeamId, TournamentId
from bracket.utils.pagination import PaginationTeams
from bracket.utils.types import dict_without_none


async def get_teams_by_id(
    conn: AsyncConnection, team_ids: set[TeamId], tournament_id: TournamentId
) -> list[Team]:
    if len(team_ids) < 1:
        return []

    query = """
        SELECT *
        FROM teams
        WHERE id = any(:team_ids)
        AND tournament_id = :tournament_id
    """
    result = await conn.execute(
        text(query), {"team_ids": list(team_ids), "tournament_id": tournament_id}
    )
    return [Team.model_validate(team._mapping) for team in result]


async def get_team_by_id(
    conn: AsyncConnection, team_id: TeamId, tournament_id: TournamentId
) -> Team | None:
    result = await get_teams_by_id(conn, {team_id}, tournament_id)
    return result[0] if len(result) > 0 else None


async def get_teams_with_members(
    conn: AsyncConnection,
    tournament_id: TournamentId,
    *,
    only_active_teams: bool = False,
    team_id: TeamId | None = None,
    pagination: PaginationTeams | None = None,
) -> list[FullTeamWithPlayers]:
    active_team_filter = "AND teams.active IS TRUE" if only_active_teams else ""
    team_id_filter = "AND teams.id = :team_id" if team_id is not None else ""
    limit_filter = "LIMIT :limit" if pagination is not None and pagination.limit is not None else ""
    offset_filter = (
        "OFFSET :offset" if pagination is not None and pagination.offset is not None else ""
    )
    sort = (
        f"teams.{pagination.sort_by} {pagination.sort_direction}"
        if pagination is not None
        else "teams.elo_score DESC, teams.wins DESC, name ASC"
    )
    query = f"""
        SELECT
            teams.*,
            to_json(array_agg(p.*)) AS players
        FROM teams
        LEFT JOIN players_x_teams pt on pt.team_id = teams.id
        LEFT JOIN players p on pt.player_id = p.id
        WHERE teams.tournament_id = :tournament_id
        {active_team_filter}
        {team_id_filter}
        GROUP BY teams.id
        ORDER BY {sort}
        {limit_filter}
        {offset_filter}
        """
    values = dict_without_none(
        {
            "tournament_id": tournament_id,
            "team_id": team_id,
            "limit": pagination.limit if pagination is not None else None,
            "offset": pagination.offset if pagination is not None else None,
        }
    )
    result = await conn.execute(text(query), values)
    return [FullTeamWithPlayers.model_validate(x._mapping) for x in result]


async def get_team_count(
    conn: AsyncConnection,
    tournament_id: TournamentId,
    *,
    only_active_teams: bool = False,
) -> int:
    active_team_filter = "AND teams.active IS TRUE" if only_active_teams else ""
    query = f"""
        SELECT count(*)
        FROM teams
        WHERE teams.tournament_id = :tournament_id
        {active_team_filter}
        """
    return int(await conn.scalar(text(query), {"tournament_id": tournament_id}) or 0)


async def update_team_stats(
    conn: AsyncConnection,
    tournament_id: TournamentId,
    stage_item_input_id: StageItemInputId,
    team_statistics: TeamStatistics,
) -> None:
    query = """
        UPDATE stage_item_inputs
        SET
            wins = :wins,
            draws = :draws,
            losses = :losses,
            points = :points
        WHERE stage_item_inputs.tournament_id = :tournament_id
        AND stage_item_inputs.id = :stage_item_input_id
        """
    await conn.execute(
        text(query),
        {
            "tournament_id": tournament_id,
            "stage_item_input_id": stage_item_input_id,
            "wins": team_statistics.wins,
            "draws": team_statistics.draws,
            "losses": team_statistics.losses,
            "points": float(team_statistics.points),
        },
    )


async def sql_delete_team(
    conn: AsyncConnection, tournament_id: TournamentId, team_id: TeamId
) -> None:
    query = "DELETE FROM teams WHERE id = :team_id AND tournament_id = :tournament_id"
    await conn.execute(text(query), {"team_id": team_id, "tournament_id": tournament_id})


async def sql_delete_teams_of_tournament(
    conn: AsyncConnection, tournament_id: TournamentId
) -> None:
    query = "DELETE FROM teams WHERE tournament_id = :tournament_id"
    await conn.execute(text(query), {"tournament_id": tournament_id})
