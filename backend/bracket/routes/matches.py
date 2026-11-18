from typing import Annotated

from fastapi import APIRouter, Depends

from bracket.config import config
from bracket.database import DbSession
from bracket.logic.matches import create_swiss_match, delete_swiss_match, record_match_result
from bracket.logic.planning.matches import delay_upcoming_matches, schedule_all_matches
from bracket.models.db.match import Match, MatchBody, MatchCreateBodyFrontend, ScheduleDelayBody
from bracket.models.db.tournament import Tournament
from bracket.models.db.user import UserPublic
from bracket.routes.access import user_authenticated_for_tournament
from bracket.routes.models import SingleMatchResponse, SuccessResponse
from bracket.routes.resources import disallow_archived_tournament, match_dependency
from bracket.utils.id_types import TournamentId

router = APIRouter(prefix=config.api_prefix)

TournamentOrganizer = Annotated[UserPublic, Depends(user_authenticated_for_tournament)]
OpenTournament = Annotated[Tournament, Depends(disallow_archived_tournament)]


@router.delete("/tournaments/{tournament_id}/matches/{match_id}", response_model=SuccessResponse)
async def delete_match(
    session: DbSession,
    _: TournamentOrganizer,
    tournament: OpenTournament,
    match: Annotated[Match, Depends(match_dependency)],
) -> SuccessResponse:
    await delete_swiss_match(session, tournament, match)
    return SuccessResponse()


@router.post("/tournaments/{tournament_id}/matches", response_model=SingleMatchResponse)
async def create_match(
    session: DbSession,
    match_body: MatchCreateBodyFrontend,
    _: TournamentOrganizer,
    tournament: OpenTournament,
) -> SingleMatchResponse:
    return SingleMatchResponse(data=await create_swiss_match(session, tournament, match_body))


@router.post("/tournaments/{tournament_id}/schedule_matches", response_model=SuccessResponse)
async def schedule_matches(
    session: DbSession,
    tournament_id: TournamentId,
    _: TournamentOrganizer,
    __: OpenTournament,
) -> SuccessResponse:
    await schedule_all_matches(session, tournament_id)
    return SuccessResponse()


@router.post("/tournaments/{tournament_id}/delay_schedule", response_model=SuccessResponse)
async def delay_schedule(
    session: DbSession,
    tournament_id: TournamentId,
    body: ScheduleDelayBody,
    _: TournamentOrganizer,
    __: OpenTournament,
) -> SuccessResponse:
    """
    Move every round that hasn't been played yet, and everything after it, for an event that
    runs late. A negative number of minutes moves them earlier.
    """
    await delay_upcoming_matches(session, tournament_id, body.minutes)
    return SuccessResponse()


@router.put("/tournaments/{tournament_id}/matches/{match_id}", response_model=SuccessResponse)
async def update_match_by_id(
    session: DbSession,
    match_body: MatchBody,
    _: TournamentOrganizer,
    tournament: OpenTournament,
    match: Annotated[Match, Depends(match_dependency)],
) -> SuccessResponse:
    await record_match_result(session, tournament, match, match_body)
    return SuccessResponse()
