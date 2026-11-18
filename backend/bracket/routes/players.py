from typing import Annotated

from fastapi import APIRouter, Depends, Query

from bracket.config import config
from bracket.database import DbSession
from bracket.logic.players import create_players, update_player
from bracket.logic.ranking.players import get_players_with_statistics
from bracket.models.db.player import PlayerBody, PlayerMultiBody
from bracket.models.db.tournament import Tournament
from bracket.models.db.user import UserPublic
from bracket.routes.access import (
    user_authenticated_for_tournament,
    user_authenticated_or_rate_limited_visitor,
)
from bracket.routes.models import (
    PaginatedPlayers,
    PlayersResponse,
    SinglePlayerResponse,
    SuccessResponse,
)
from bracket.routes.resources import disallow_archived_tournament
from bracket.sql.players import get_player_count, sql_delete_player
from bracket.utils.id_types import PlayerId, TournamentId
from bracket.utils.pagination import ParticipantPagination

router = APIRouter(prefix=config.api_prefix)

TournamentOrganizer = Annotated[UserPublic, Depends(user_authenticated_for_tournament)]
OpenTournament = Annotated[Tournament, Depends(disallow_archived_tournament)]


@router.get("/tournaments/{tournament_id}/players", response_model=PlayersResponse)
async def get_players(
    session: DbSession,
    tournament_id: TournamentId,
    pagination: Annotated[ParticipantPagination, Query()],
    _: Annotated[UserPublic | None, Depends(user_authenticated_or_rate_limited_visitor)],
    not_in_team: bool = False,
) -> PlayersResponse:
    return PlayersResponse(
        data=PaginatedPlayers(
            players=await get_players_with_statistics(
                session, tournament_id, not_in_team=not_in_team, pagination=pagination
            ),
            count=await get_player_count(session, tournament_id, not_in_team=not_in_team),
        )
    )


@router.put("/tournaments/{tournament_id}/players/{player_id}", response_model=SinglePlayerResponse)
async def update_player_by_id(
    session: DbSession,
    tournament_id: TournamentId,
    player_id: PlayerId,
    player_body: PlayerBody,
    _: TournamentOrganizer,
    __: OpenTournament,
) -> SinglePlayerResponse:
    return SinglePlayerResponse(
        data=await update_player(session, tournament_id, player_id, player_body)
    )


@router.delete("/tournaments/{tournament_id}/players/{player_id}", response_model=SuccessResponse)
async def delete_player(
    session: DbSession,
    tournament_id: TournamentId,
    player_id: PlayerId,
    _: TournamentOrganizer,
    __: OpenTournament,
) -> SuccessResponse:
    await sql_delete_player(session, tournament_id, player_id)
    return SuccessResponse()


@router.post("/tournaments/{tournament_id}/players", response_model=SuccessResponse)
async def create_single_player(
    session: DbSession,
    player_body: PlayerBody,
    tournament_id: TournamentId,
    user: TournamentOrganizer,
    _: OpenTournament,
) -> SuccessResponse:
    await create_players(
        session, tournament_id, [player_body.name], active=player_body.active, user=user
    )
    return SuccessResponse()


@router.post("/tournaments/{tournament_id}/players_multi", response_model=SuccessResponse)
async def create_multiple_players(
    session: DbSession,
    player_body: PlayerMultiBody,
    tournament_id: TournamentId,
    user: TournamentOrganizer,
    _: OpenTournament,
) -> SuccessResponse:
    await create_players(
        session, tournament_id, player_body.player_names, active=player_body.active, user=user
    )
    return SuccessResponse()
