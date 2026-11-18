from typing import Annotated

from fastapi import APIRouter, Depends

from bracket.config import config
from bracket.database import DbSession
from bracket.logic.clubs import (
    add_club_member,
    create_owned_club,
    remove_club_member,
    rename_club,
    transfer_club_ownership,
)
from bracket.models.db.club import (
    ClubCreateBody,
    ClubMemberCreateBody,
    ClubOwnerUpdateBody,
    ClubUpdateBody,
)
from bracket.models.db.user import UserPublic
from bracket.routes.access import (
    AuthenticatedUser,
    user_authenticated_for_club,
    user_owns_club,
)
from bracket.routes.models import (
    ClubMembersResponse,
    ClubResponse,
    ClubsResponse,
    SuccessResponse,
)
from bracket.sql.clubs import get_club_members, get_clubs_for_user_id, sql_delete_club
from bracket.utils.errors import ForeignKey, check_foreign_key_violation
from bracket.utils.id_types import ClubId, UserId
from bracket.utils.rate_limit import rate_limit

router = APIRouter(prefix=config.api_prefix)

ClubOrganizer = Annotated[UserPublic, Depends(user_authenticated_for_club)]
ClubOwner = Annotated[UserPublic, Depends(user_owns_club)]


@router.get("/clubs", response_model=ClubsResponse)
async def get_clubs(session: DbSession, user: AuthenticatedUser) -> ClubsResponse:
    return ClubsResponse(data=await get_clubs_for_user_id(session, user.id))


@router.post("/clubs", response_model=ClubResponse)
async def create_new_club(
    session: DbSession, club: ClubCreateBody, user: AuthenticatedUser
) -> ClubResponse:
    return ClubResponse(data=await create_owned_club(session, club, user))


@router.delete("/clubs/{club_id}", response_model=SuccessResponse)
async def delete_club(session: DbSession, club_id: ClubId, _: ClubOwner) -> SuccessResponse:
    with check_foreign_key_violation({ForeignKey.tournaments_club_id_fkey}):
        await sql_delete_club(session, club_id)

    return SuccessResponse()


@router.put("/clubs/{club_id}", response_model=ClubResponse)
async def update_club(
    session: DbSession, club_id: ClubId, club: ClubUpdateBody, user: ClubOwner
) -> ClubResponse:
    return ClubResponse(data=await rename_club(session, club_id, club, user))


@router.put("/clubs/{club_id}/owner", response_model=ClubMembersResponse)
async def transfer_ownership(
    session: DbSession, club_id: ClubId, body: ClubOwnerUpdateBody, _: ClubOwner
) -> ClubMembersResponse:
    """
    Hand the event over to another of its organizers, for an owner who leaves the organizing
    team. The previous owner stays on as an organizer.
    """
    return ClubMembersResponse(data=await transfer_club_ownership(session, club_id, body.user_id))


@router.get("/clubs/{club_id}/members", response_model=ClubMembersResponse)
async def get_members(session: DbSession, club_id: ClubId, _: ClubOrganizer) -> ClubMembersResponse:
    """The organizers of an event: its owner and the people the owner added."""
    return ClubMembersResponse(data=await get_club_members(session, club_id))


@router.post(
    "/clubs/{club_id}/members",
    response_model=ClubMembersResponse,
    dependencies=[Depends(rate_limit("20/5minutes"))],
)
async def add_member(
    session: DbSession, club_id: ClubId, body: ClubMemberCreateBody, _: ClubOwner
) -> ClubMembersResponse:
    """
    Let another account help run this event and its tournaments, so that organizers don't have
    to share one login.
    """
    return ClubMembersResponse(data=await add_club_member(session, club_id, body.email))


@router.delete("/clubs/{club_id}/members/{user_id}", response_model=ClubMembersResponse)
async def remove_member(
    session: DbSession, club_id: ClubId, user_id: UserId, user: ClubOrganizer
) -> ClubMembersResponse:
    """Remove an organizer from the event. The owner removes others; anyone can leave."""
    return ClubMembersResponse(data=await remove_club_member(session, club_id, user_id, user))
