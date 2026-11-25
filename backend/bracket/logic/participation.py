"""
How teams take part in a tournament, and how its lineup follows their rosters.

A player can be an active member of one team at most among the teams of a tournament. The
primary key of `tournament_players` enforces that, and `follow_rosters` says who breaks it.

The commands that make lineups follow rosters take their locks in one order: first the tournaments
whose lineups they write, then the teams whose rosters they read. A tournament command already
holds its tournament's lock; one that adds teams or reopens the tournament then locks those teams
against changes (`lock_teams_against_changes`). A command that changes a roster is the exception:
it locks the team, and then the team's open tournaments (see `bracket.logic.teams`). That can't
deadlock, because it only waits for tournaments that the team takes part in and that are open,
while a tournament command only waits for teams that are joining it, or whose tournament is
being reopened.
"""

from collections.abc import Iterable
from operator import attrgetter

from fastapi import HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from starlette import status

from bracket.logic.ranking.team_totals import get_team_totals, with_totals
from bracket.logic.subscriptions import Limit, check_requirement
from bracket.models.db.participation import TournamentTeam, TournamentTeamWithPlayers
from bracket.models.db.team import TeamMultiBody
from bracket.models.db.tournament import Tournament
from bracket.models.db.user import UserPublic
from bracket.models.results import ResultTotals
from bracket.sql.participation import (
    LineupScope,
    find_lineup_clash,
    get_participating_team_ids,
    get_tournament_team,
    get_tournament_teams,
    sql_add_tournament_teams,
    sql_remove_tournament_team,
    sql_set_tournament_team_active,
    sync_lineups,
)
from bracket.sql.players import get_players_by_name, insert_players
from bracket.sql.teams import lock_teams_against_changes, sql_add_team_members, sql_create_team
from bracket.sql.validation import validate_team_ids
from bracket.utils.errors import (
    ForeignKey,
    UniqueIndex,
    check_foreign_key_violation,
    check_unique_constraint_violation,
)
from bracket.utils.i18n import gettext
from bracket.utils.id_types import PlayerId, TeamId, TournamentId
from bracket.utils.pagination import TeamPagination
from bracket.utils.types import assert_some


async def get_tournament_teams_with_totals(
    session: AsyncSession,
    tournament_id: TournamentId,
    *,
    pagination: TeamPagination | None = None,
    totals: dict[TeamId, ResultTotals] | None = None,
) -> list[TournamentTeamWithPlayers]:
    """
    The teams that take part, with their lineups and replayed results. Without `pagination`, the
    best first.

    Results aren't stored, so sorting by them happens here, before the page is cut. `totals` can
    be passed by a caller that has them.
    """
    teams = await get_tournament_teams(
        session,
        tournament_id,
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


async def get_tournament_team_with_totals(
    session: AsyncSession, tournament_id: TournamentId, team_id: TeamId
) -> TournamentTeam:
    team = assert_some(await get_tournament_team(session, tournament_id, team_id))
    return with_totals(team, await get_team_totals(session, tournament_id))


async def follow_rosters(session: AsyncSession, scope: LineupScope) -> None:
    """
    Make the scope's lineups follow their teams' active members, unless a player would then play
    for two teams of a tournament.
    """
    clash = await find_lineup_clash(session, scope)
    if clash is not None:
        first, second = clash.team_names
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=gettext(
                "{player} can't play for both {first} and {second} in {tournament}. A player can "
                "be an active member of only one of a tournament's teams.",
                player=clash.player_name,
                first=first,
                second=second,
                tournament=clash.tournament_name,
            ),
        )
    # Another command can still change the same lineup in the meantime.
    with check_unique_constraint_violation({UniqueIndex.tournament_players_pkey}):
        await sync_lineups(session, scope)


async def add_teams(
    session: AsyncSession, tournament: Tournament, team_ids: set[TeamId], user: UserPublic
) -> None:
    """Let these teams take part in the tournament. Their active members join its lineup."""
    await validate_team_ids(session, team_ids)
    taking_part = await get_participating_team_ids(session, tournament.id)
    if team_ids & taking_part:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=gettext("Some of these teams already take part in this tournament"),
        )
    check_requirement(Limit.TEAMS, len(taking_part), user, additions=len(team_ids))

    await lock_teams_against_changes(session, team_ids)
    with check_unique_constraint_violation({UniqueIndex.tournament_teams_pkey}):
        await sql_add_tournament_teams(session, tournament.id, team_ids)
    await follow_rosters(session, LineupScope.of_tournament(tournament.id))


async def create_teams_with_players(
    session: AsyncSession, tournament: Tournament, body: TeamMultiBody, user: UserPublic
) -> None:
    """
    Create teams from a list, with their players as active members, and let them take part in
    the tournament.

    A listed name that one player already has, regardless of case, is that player: someone who
    plays in several tournaments is then the same player in all of them, which the schedule takes
    into account. Other names become new players.
    """
    teams = [
        (team_name, _unique_names(player_names))
        for team_name, player_names in body.teams_with_players
    ]
    check_requirement(
        Limit.TEAMS,
        len(await get_participating_team_ids(session, tournament.id)),
        user,
        additions=len(teams),
    )
    for _, player_names in teams:
        check_requirement(Limit.PLAYERS, 0, user, additions=len(player_names))

    player_ids = await _players_named(
        session, _unique_names(name for _, player_names in teams for name in player_names)
    )
    team_ids = []
    for team_name, player_names in teams:
        team_id = await sql_create_team(session, team_name)
        await sql_add_team_members(
            session, team_id, [player_ids[name.lower()] for name in player_names]
        )
        team_ids.append(team_id)
    await sql_add_tournament_teams(session, tournament.id, team_ids)
    await follow_rosters(session, LineupScope.of_tournament(tournament.id))


def _unique_names(names: Iterable[str]) -> list[str]:
    """The names in order, each once regardless of case, as first spelled."""
    unique: dict[str, str] = {}
    for name in names:
        unique.setdefault(name.lower(), name)
    return list(unique.values())


async def _players_named(session: AsyncSession, names: list[str]) -> dict[str, PlayerId]:
    """
    The player with each name, by the name in lowercase. Names that no player has yet become new
    players; a name that several players have is refused, as it doesn't say which one.
    """
    existing = await get_players_by_name(session, names)
    ambiguous = [name for name in names if len(existing.get(name.lower(), [])) > 1]
    if ambiguous:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=gettext(
                "Several players are called {name}. Add that player to the team in Teams and "
                "players, where you can choose which of them it is.",
                name=ambiguous[0],
            ),
        )

    new_names = [name for name in names if name.lower() not in existing]
    new_ids = await insert_players(session, new_names)
    return {name: players[0].id for name, players in existing.items()} | {
        name.lower(): player_id for name, player_id in zip(new_names, new_ids, strict=True)
    }


async def set_team_active(
    session: AsyncSession, tournament_id: TournamentId, team_id: TeamId, *, active: bool
) -> TournamentTeam:
    """Whether the team plays the rounds still to come. Swiss rounds pair active teams only."""
    await sql_set_tournament_team_active(session, tournament_id, team_id, active)
    return await get_tournament_team_with_totals(session, tournament_id, team_id)


async def remove_team(session: AsyncSession, tournament_id: TournamentId, team_id: TeamId) -> None:
    """The team leaves the tournament, and its players the lineup. One with a slot can't."""
    with check_foreign_key_violation({ForeignKey.stage_item_inputs_team_id_fkey}):
        await sql_remove_tournament_team(session, tournament_id, team_id)
