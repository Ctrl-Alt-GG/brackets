"""The teams that take part in a tournament, and the players who play for them there."""

from typing import Annotated

from fastapi import APIRouter, Depends, Query

from bracket import orm
from bracket.config import config
from bracket.database import DbSession
from bracket.logic import participation as participation_logic
from bracket.logic.ranking.players import get_players_with_statistics
from bracket.models.db.participation import (
    TournamentTeam,
    TournamentTeamBody,
    TournamentTeamsBody,
)
from bracket.models.db.team import TeamMultiBody
from bracket.models.db.tournament import Tournament
from bracket.models.db.user import UserPublic
from bracket.routes.access import (
    user_authenticated_for_tournament,
    user_authenticated_or_rate_limited_visitor,
)
from bracket.routes.models import (
    PaginatedTournamentPlayers,
    PaginatedTournamentTeams,
    SuccessResponse,
    TournamentPlayersResponse,
    TournamentTeamResponse,
    TournamentTeamsResponse,
)
from bracket.routes.resources import disallow_archived_tournament, tournament_team_dependency
from bracket.sql.tournaments import count_tournament_records
from bracket.utils.id_types import TournamentId
from bracket.utils.pagination import PlayerPagination, TeamPagination

router = APIRouter(prefix=config.api_prefix)

TournamentOrganizer = Annotated[UserPublic, Depends(user_authenticated_for_tournament)]
OrganizerOrVisitor = Annotated[
    UserPublic | None, Depends(user_authenticated_or_rate_limited_visitor)
]
OpenTournament = Annotated[Tournament, Depends(disallow_archived_tournament)]
ParticipatingTeam = Annotated[TournamentTeam, Depends(tournament_team_dependency)]


@router.get("/tournaments/{tournament_id}/teams", response_model=TournamentTeamsResponse)
async def get_tournament_teams(
    session: DbSession,
    tournament_id: TournamentId,
    pagination: Annotated[TeamPagination, Query()],
    _: OrganizerOrVisitor,
) -> TournamentTeamsResponse:
    """The teams that take part, with their lineups and their results in the tournament."""
    return TournamentTeamsResponse(
        data=PaginatedTournamentTeams(
            teams=await participation_logic.get_tournament_teams_with_totals(
                session, tournament_id, pagination=pagination
            ),
            count=await count_tournament_records(session, orm.TournamentTeam, tournament_id),
        )
    )


@router.post("/tournaments/{tournament_id}/teams", response_model=SuccessResponse)
async def add_tournament_teams(
    session: DbSession,
    body: TournamentTeamsBody,
    user: TournamentOrganizer,
    tournament: OpenTournament,
) -> SuccessResponse:
    """
    Let these teams take part. Their active members join the tournament's lineup, unless one of
    them already plays for another of its teams.
    """
    await participation_logic.add_teams(session, tournament, body.team_ids, user)
    return SuccessResponse()


@router.post("/tournaments/{tournament_id}/teams_multi", response_model=SuccessResponse)
async def create_tournament_teams(
    session: DbSession,
    body: TeamMultiBody,
    user: TournamentOrganizer,
    tournament: OpenTournament,
) -> SuccessResponse:
    """
    Create teams from a list and let them take part. A player whose name is already taken,
    regardless of case, joins as that player.
    """
    await participation_logic.create_teams_with_players(session, tournament, body, user)
    return SuccessResponse()


@router.put("/tournaments/{tournament_id}/teams/{team_id}", response_model=TournamentTeamResponse)
async def update_tournament_team(
    session: DbSession,
    tournament_id: TournamentId,
    body: TournamentTeamBody,
    _: TournamentOrganizer,
    __: OpenTournament,
    team: ParticipatingTeam,
) -> TournamentTeamResponse:
    return TournamentTeamResponse(
        data=await participation_logic.set_team_active(
            session, tournament_id, team.id, active=body.active
        )
    )


@router.delete("/tournaments/{tournament_id}/teams/{team_id}", response_model=SuccessResponse)
async def remove_tournament_team(
    session: DbSession,
    tournament_id: TournamentId,
    _: TournamentOrganizer,
    __: OpenTournament,
    team: ParticipatingTeam,
) -> SuccessResponse:
    """The team leaves the tournament. One that has a slot in a stage can't."""
    await participation_logic.remove_team(session, tournament_id, team.id)
    return SuccessResponse()


@router.get("/tournaments/{tournament_id}/players", response_model=TournamentPlayersResponse)
async def get_tournament_players(
    session: DbSession,
    tournament_id: TournamentId,
    pagination: Annotated[PlayerPagination, Query()],
    _: OrganizerOrVisitor,
) -> TournamentPlayersResponse:
    """The tournament's lineup: its players, the teams they play for, and their results."""
    return TournamentPlayersResponse(
        data=PaginatedTournamentPlayers(
            players=await get_players_with_statistics(
                session, tournament_id, pagination=pagination
            ),
            count=await count_tournament_records(session, orm.TournamentPlayer, tournament_id),
        )
    )
