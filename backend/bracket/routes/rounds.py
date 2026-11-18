from typing import Annotated

from fastapi import APIRouter, Depends

from bracket.config import config
from bracket.database import DbSession
from bracket.logic.rounds import (
    create_swiss_round,
    delete_swiss_round,
    regenerate_swiss_round,
    update_round,
)
from bracket.models.db.round import Round, RoundCreateBody, RoundUpdateBody
from bracket.models.db.stage_tree import RoundWithMatches
from bracket.models.db.tournament import Tournament
from bracket.models.db.user import UserPublic
from bracket.routes.access import user_authenticated_for_tournament
from bracket.routes.models import SuccessResponse
from bracket.routes.resources import (
    disallow_archived_tournament,
    round_dependency,
    round_with_matches_dependency,
)
from bracket.utils.id_types import TournamentId

router = APIRouter(prefix=config.api_prefix)

TournamentOrganizer = Annotated[UserPublic, Depends(user_authenticated_for_tournament)]
OpenTournament = Annotated[Tournament, Depends(disallow_archived_tournament)]
LoadedRoundWithMatches = Annotated[RoundWithMatches, Depends(round_with_matches_dependency)]


@router.delete("/tournaments/{tournament_id}/rounds/{round_id}", response_model=SuccessResponse)
async def delete_round(
    session: DbSession,
    _: TournamentOrganizer,
    tournament: OpenTournament,
    round_with_matches: LoadedRoundWithMatches,
) -> SuccessResponse:
    await delete_swiss_round(session, tournament, round_with_matches)
    return SuccessResponse()


@router.post("/tournaments/{tournament_id}/rounds", response_model=SuccessResponse)
async def create_round(
    session: DbSession,
    round_body: RoundCreateBody,
    user: TournamentOrganizer,
    tournament: OpenTournament,
) -> SuccessResponse:
    """
    Create the next round of a Swiss stage item as a draft in which every active team is paired.

    Only organizers see the draft. Its pairings can be changed by adding and deleting matches, and
    it is published by updating the round with `is_draft` set to false.
    """
    await create_swiss_round(session, tournament, round_body, user)
    return SuccessResponse()


@router.post(
    "/tournaments/{tournament_id}/rounds/{round_id}/regenerate", response_model=SuccessResponse
)
async def regenerate_round(
    session: DbSession,
    _: TournamentOrganizer,
    tournament: OpenTournament,
    round_: LoadedRoundWithMatches,
) -> SuccessResponse:
    """Replace a Swiss draft in one transaction, retaining it if any replacement fails."""
    await regenerate_swiss_round(session, tournament, round_)
    return SuccessResponse()


@router.put("/tournaments/{tournament_id}/rounds/{round_id}", response_model=SuccessResponse)
async def update_round_by_id(
    session: DbSession,
    tournament_id: TournamentId,
    round_body: RoundUpdateBody,
    _: TournamentOrganizer,
    round_: Annotated[Round, Depends(round_dependency)],
    ___: OpenTournament,
) -> SuccessResponse:
    """
    Rename a round, or publish or withdraw a draft. Only Swiss rounds can be drafts: the rounds of
    the other formats are published with their stage item, and a withdrawn one couldn't be
    published again.
    """
    await update_round(session, tournament_id, round_, round_body)
    return SuccessResponse()
