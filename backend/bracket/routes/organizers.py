from typing import Annotated

from fastapi import APIRouter, Depends

from bracket.config import config
from bracket.database import DbSession
from bracket.logic.organizers import add_organizer, remove_organizer, transfer_ownership
from bracket.models.db.organizer import OrganizerCreateBody, OwnerUpdateBody
from bracket.models.db.user import UserPublic
from bracket.routes.access import user_authenticated_for_tournament, user_owns_tournament
from bracket.routes.models import OrganizersResponse
from bracket.sql.organizers import get_organizers
from bracket.utils.id_types import TournamentId, UserId
from bracket.utils.rate_limit import rate_limit

router = APIRouter(prefix=config.api_prefix)

TournamentOrganizer = Annotated[UserPublic, Depends(user_authenticated_for_tournament)]
TournamentOwner = Annotated[UserPublic, Depends(user_owns_tournament)]


@router.get("/tournaments/{tournament_id}/organizers", response_model=OrganizersResponse)
async def get_tournament_organizers(
    session: DbSession, tournament_id: TournamentId, _: TournamentOrganizer
) -> OrganizersResponse:
    """Who runs the tournament: its owner, and the accounts the owner added to help."""
    return OrganizersResponse(data=await get_organizers(session, tournament_id))


@router.post(
    "/tournaments/{tournament_id}/organizers",
    response_model=OrganizersResponse,
    dependencies=[Depends(rate_limit("20/5minutes"))],
)
async def add_tournament_organizer(
    session: DbSession, tournament_id: TournamentId, body: OrganizerCreateBody, _: TournamentOwner
) -> OrganizersResponse:
    """Let another account help run the tournament, so that organizers don't share a login."""
    return OrganizersResponse(data=await add_organizer(session, tournament_id, body.email))


@router.delete(
    "/tournaments/{tournament_id}/organizers/{user_id}", response_model=OrganizersResponse
)
async def remove_tournament_organizer(
    session: DbSession, tournament_id: TournamentId, user_id: UserId, user: TournamentOrganizer
) -> OrganizersResponse:
    """Remove an organizer from the tournament. The owner removes others; anyone can leave."""
    return OrganizersResponse(data=await remove_organizer(session, tournament_id, user_id, user))


@router.put("/tournaments/{tournament_id}/owner", response_model=OrganizersResponse)
async def transfer_tournament_ownership(
    session: DbSession, tournament_id: TournamentId, body: OwnerUpdateBody, _: TournamentOwner
) -> OrganizersResponse:
    """
    Hand the tournament over to another of its organizers, for an owner who leaves the organizing
    team. The previous owner stays on as an organizer.
    """
    return OrganizersResponse(data=await transfer_ownership(session, tournament_id, body.user_id))
