from typing import Annotated

from fastapi import APIRouter, Depends

from bracket.config import config
from bracket.database import DbSession
from bracket.logic import rankings as ranking_logic
from bracket.logic.tournaments import get_tournament_standings
from bracket.models.db.ranking import Ranking, RankingBody, RankingCreateBody
from bracket.models.db.tournament import Tournament
from bracket.models.db.user import UserPublic
from bracket.routes.access import (
    user_authenticated_for_tournament,
    user_authenticated_or_rate_limited_visitor,
)
from bracket.routes.models import (
    RankingsResponse,
    StandingsResponse,
    SuccessResponse,
)
from bracket.routes.resources import disallow_archived_tournament, ranking_dependency
from bracket.sql.rankings import get_all_rankings_in_tournament
from bracket.utils.id_types import RankingId, TournamentId

router = APIRouter(prefix=config.api_prefix)

TournamentOrganizer = Annotated[UserPublic, Depends(user_authenticated_for_tournament)]
OrganizerOrVisitor = Annotated[
    UserPublic | None, Depends(user_authenticated_or_rate_limited_visitor)
]
OpenTournament = Annotated[Tournament, Depends(disallow_archived_tournament)]
LoadedRanking = Annotated[Ranking, Depends(ranking_dependency)]


@router.get("/tournaments/{tournament_id}/rankings")
async def get_rankings(
    session: DbSession, tournament_id: TournamentId, _: OrganizerOrVisitor
) -> RankingsResponse:
    return RankingsResponse(data=await get_all_rankings_in_tournament(session, tournament_id))


@router.get("/tournaments/{tournament_id}/standings")
async def get_standings(
    session: DbSession, tournament_id: TournamentId, _: OrganizerOrVisitor
) -> StandingsResponse:
    """
    Get the teams of every stage item, best first. Teams advance to the next stage in this order.
    """
    return StandingsResponse(data=await get_tournament_standings(session, tournament_id))


@router.put("/tournaments/{tournament_id}/rankings/{ranking_id}")
async def update_ranking_by_id(
    session: DbSession,
    tournament_id: TournamentId,
    ranking_id: RankingId,
    ranking_body: RankingBody,
    _: TournamentOrganizer,
    __: OpenTournament,
    ___: LoadedRanking,
) -> SuccessResponse:
    await ranking_logic.update_ranking(session, tournament_id, ranking_id, ranking_body)
    return SuccessResponse()


@router.delete("/tournaments/{tournament_id}/rankings/{ranking_id}")
async def delete_ranking(
    session: DbSession,
    tournament_id: TournamentId,
    ranking_id: RankingId,
    _: TournamentOrganizer,
    __: OpenTournament,
    ___: LoadedRanking,
) -> SuccessResponse:
    await ranking_logic.delete_ranking(session, tournament_id, ranking_id)
    return SuccessResponse()


@router.post("/tournaments/{tournament_id}/rankings")
async def create_ranking(
    session: DbSession,
    ranking_body: RankingCreateBody,
    tournament_id: TournamentId,
    user: TournamentOrganizer,
    _: OpenTournament,
) -> SuccessResponse:
    await ranking_logic.create_ranking(session, tournament_id, ranking_body, user)
    return SuccessResponse()
