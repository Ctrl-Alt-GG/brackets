"""Teams with their results, and their rosters."""

from collections.abc import Mapping
from operator import attrgetter

from fastapi import HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from starlette import status

from bracket.logic.ranking.team_totals import get_team_totals, with_totals
from bracket.logic.subscriptions import Limit, check_requirement
from bracket.models.db.team import FullTeamWithPlayers, Team, TeamBody, TeamMultiBody
from bracket.models.db.tournament import Tournament
from bracket.models.db.user import UserPublic
from bracket.models.results import ResultTotals
from bracket.sql.players import get_player_count, insert_players
from bracket.sql.teams import (
    find_player_in_other_team,
    get_team_by_id,
    get_team_count,
    get_team_player_ids,
    get_teams_with_members,
    sql_add_team_players,
    sql_create_team,
    sql_replace_team_members,
    sql_update_team,
)
from bracket.sql.validation import validate_player_ids
from bracket.utils.id_types import PlayerId, TeamId, TournamentId
from bracket.utils.pagination import ParticipantPagination
from bracket.utils.types import assert_some


async def get_teams_with_totals(
    session: AsyncSession,
    tournament_id: TournamentId,
    *,
    only_active_teams: bool = False,
    team_id: TeamId | None = None,
    pagination: ParticipantPagination | None = None,
    totals: Mapping[TeamId, ResultTotals] | None = None,
) -> list[FullTeamWithPlayers]:
    """
    The teams with their players and replayed results. Without `pagination`, the best first.

    Results aren't stored, so sorting by them happens here, before the page is cut. `totals` can
    be passed by a caller that has them.
    """
    teams = await get_teams_with_members(
        session,
        tournament_id,
        only_active_teams=only_active_teams,
        team_id=team_id,
        pagination=pagination
        if pagination is not None and not pagination.sorts_by_results
        else None,
    )
    if not teams:
        return []
    if totals is None:
        totals = await get_team_totals(session, tournament_id)
    teams = [with_totals(team, totals) for team in teams]

    if pagination is None:
        teams.sort(key=lambda team: (-team.elo_score, -team.wins, team.name, team.id))
    elif pagination.sorts_by_results:
        teams.sort(key=attrgetter(pagination.sort_by), reverse=pagination.sort_direction == "desc")
        teams = teams[pagination.offset : pagination.offset + pagination.limit]
    return teams


async def get_team_with_totals(
    session: AsyncSession, tournament_id: TournamentId, team_id: TeamId
) -> Team:
    team = assert_some(await get_team_by_id(session, team_id, tournament_id))
    return with_totals(team, await get_team_totals(session, tournament_id))


async def check_players_are_free(
    session: AsyncSession, team_id: TeamId, tournament: Tournament, player_ids: set[PlayerId]
) -> None:
    """Unless the tournament allows it, a player who joins a team isn't in another one."""
    if tournament.players_can_be_in_multiple_teams or len(player_ids) < 1:
        return

    taken = await find_player_in_other_team(session, tournament.id, team_id, player_ids)
    if taken is not None:
        player, team_name = taken
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=(
                f"{player.name} is already in {team_name}. Players can be in one team, "
                "unless the tournament's settings allow more."
            ),
        )


async def replace_team_members(
    session: AsyncSession, tournament: Tournament, team_id: TeamId, player_ids: set[PlayerId]
) -> None:
    """Make these players the team's roster."""
    await validate_player_ids(session, tournament.id, player_ids)
    previous_ids = await get_team_player_ids(session, tournament.id, team_id)
    # Players who are already in the team stay in it. A tournament from before this rule, or one
    # that allowed several teams for a while, can have them in a second team, and its teams must
    # still be saveable.
    await check_players_are_free(session, team_id, tournament, player_ids - previous_ids)
    await sql_replace_team_members(session, tournament.id, team_id, player_ids)


async def create_team(
    session: AsyncSession, tournament: Tournament, body: TeamBody, user: UserPublic
) -> Team:
    check_requirement(Limit.TEAMS, await get_team_count(session, tournament.id), user)

    team_id = await sql_create_team(session, tournament.id, body.name, body.active)
    await replace_team_members(session, tournament, team_id, body.player_ids)
    return await get_team_with_totals(session, tournament.id, team_id)


async def update_team(
    session: AsyncSession, tournament: Tournament, team_id: TeamId, body: TeamBody
) -> Team:
    await sql_update_team(session, tournament.id, team_id, body)
    await replace_team_members(session, tournament, team_id, body.player_ids)
    return await get_team_with_totals(session, tournament.id, team_id)


async def create_teams_with_players(
    session: AsyncSession, tournament_id: TournamentId, body: TeamMultiBody, user: UserPublic
) -> None:
    """Create teams, each with new players."""
    teams_with_players = body.teams_with_players
    check_requirement(
        Limit.TEAMS,
        await get_team_count(session, tournament_id),
        user,
        additions=len(teams_with_players),
    )
    check_requirement(
        Limit.PLAYERS,
        await get_player_count(session, tournament_id),
        user,
        additions=sum(len(player_names) for _, player_names in teams_with_players),
    )

    for team_name, player_names in teams_with_players:
        team_id = await sql_create_team(session, tournament_id, team_name, body.active)
        if player_names:
            player_ids = await insert_players(
                session, tournament_id, player_names, active=body.active
            )
            await sql_add_team_players(session, tournament_id, team_id, player_ids)
