from fastapi import APIRouter, Depends, HTTPException, Response
from starlette import status
from starlette.requests import Request

from bracket.config import config
from bracket.database import DbSession
from bracket.logic.subscriptions import check_requirement
from bracket.models.db.club import (
    ClubCreateBody,
    ClubMemberCreateBody,
    ClubOwnerUpdateBody,
    ClubUpdateBody,
)
from bracket.models.db.user import UserPublic
from bracket.models.db.user_x_club import UserXClubRelation
from bracket.routes.auth import forbidden, user_authenticated, user_authenticated_for_club
from bracket.routes.models import (
    ClubMembersResponse,
    ClubResponse,
    ClubsResponse,
    SuccessResponse,
)
from bracket.sql.clubs import (
    create_club,
    get_club_by_id,
    get_club_members,
    get_clubs_for_user_id,
    sql_delete_club,
    sql_give_user_access_to_club,
    sql_make_club_owner,
    sql_remove_user_from_club,
    sql_update_club,
)
from bracket.sql.users import get_user
from bracket.utils.errors import (
    ForeignKey,
    check_foreign_key_violation,
)
from bracket.utils.id_types import ClubId, UserId
from bracket.utils.rate_limit import limiter

router = APIRouter(prefix=config.api_prefix)


async def name_is_taken(
    conn: DbSession, user_id: UserId, name: str, club_id: ClubId | None = None
) -> bool:
    """
    The events an organizer owns have different names. Others may use the same ones, also the
    owners of events the organizer only helps with.
    """
    return any(
        club.name.casefold() == name.casefold() and club.id != club_id
        for club in await get_clubs_for_user_id(conn, user_id, UserXClubRelation.OWNER)
    )


async def check_name_is_free(
    conn: DbSession, user: UserPublic, name: str, club_id: ClubId | None = None
) -> None:
    if await name_is_taken(conn, user.id, name, club_id):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="You already have an event with this name",
        )


async def user_owns_club(
    club_id: ClubId, conn: DbSession, user: UserPublic = Depends(user_authenticated_for_club)
) -> UserPublic:
    """The event's owner. Organizers who were added to help can't rename it or manage who helps."""
    members = await get_club_members(conn, club_id)
    if not any(
        member.user_id == user.id and member.relation is UserXClubRelation.OWNER
        for member in members
    ):
        raise forbidden("Only the owner of this event can do that")

    return user


@router.get("/clubs", response_model=ClubsResponse)
async def get_clubs(
    conn: DbSession, user: UserPublic = Depends(user_authenticated)
) -> ClubsResponse:
    return ClubsResponse(data=await get_clubs_for_user_id(conn, user.id))


@router.post("/clubs", response_model=ClubResponse)
async def create_new_club(
    conn: DbSession, club: ClubCreateBody, user: UserPublic = Depends(user_authenticated)
) -> ClubResponse:
    existing_clubs = await get_clubs_for_user_id(conn, user.id)
    check_requirement(existing_clubs, user, "max_clubs")
    await check_name_is_free(conn, user, club.name)

    return ClubResponse(data=await create_club(conn, club, user.id))


@router.delete("/clubs/{club_id}", response_model=SuccessResponse)
async def delete_club(
    conn: DbSession, club_id: ClubId, _: UserPublic = Depends(user_owns_club)
) -> SuccessResponse:
    with check_foreign_key_violation({ForeignKey.tournaments_club_id_fkey}):
        await sql_delete_club(conn, club_id)

    return SuccessResponse()


@router.put("/clubs/{club_id}", response_model=ClubResponse)
async def update_club(
    conn: DbSession,
    club_id: ClubId,
    club: ClubUpdateBody,
    user: UserPublic = Depends(user_owns_club),
) -> ClubResponse:
    await check_name_is_free(conn, user, club.name, club_id)
    return ClubResponse(data=await sql_update_club(conn, club_id, club))


@router.put("/clubs/{club_id}/owner", response_model=ClubMembersResponse)
async def transfer_ownership(
    conn: DbSession,
    club_id: ClubId,
    body: ClubOwnerUpdateBody,
    _: UserPublic = Depends(user_owns_club),
) -> ClubMembersResponse:
    """
    Hand the event over to another of its organizers, for an owner who leaves the organizing
    team. The previous owner stays on as an organizer.
    """
    members = await get_club_members(conn, club_id)
    new_owner = next((member for member in members if member.user_id == body.user_id), None)
    if new_owner is None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Only an organizer of the event can become its owner. Add them first.",
        )
    if new_owner.relation is UserXClubRelation.OWNER:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail=f"{new_owner.name} owns it already"
        )

    club = await get_club_by_id(conn, club_id)
    if await name_is_taken(conn, new_owner.user_id, club.name, club_id):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=(
                f"{new_owner.name} already owns an event called {club.name}. Rename one of them "
                "first."
            ),
        )

    await sql_make_club_owner(conn, club_id, new_owner.user_id)
    return ClubMembersResponse(data=await get_club_members(conn, club_id))


@router.get("/clubs/{club_id}/members", response_model=ClubMembersResponse)
async def get_members(
    conn: DbSession, club_id: ClubId, _: UserPublic = Depends(user_authenticated_for_club)
) -> ClubMembersResponse:
    """The organizers of an event: its owner and the people the owner added."""
    return ClubMembersResponse(data=await get_club_members(conn, club_id))


@router.post("/clubs/{club_id}/members", response_model=ClubMembersResponse)
@limiter.limit("20/5minutes")
async def add_member(
    request: Request,
    # The rate limiter writes its headers to this.
    response: Response,
    conn: DbSession,
    club_id: ClubId,
    body: ClubMemberCreateBody,
    _: UserPublic = Depends(user_owns_club),
) -> ClubMembersResponse:
    """
    Let another account help run this event and its tournaments, so that organizers don't have
    to share one login.
    """
    del request, response

    user = await get_user(conn, body.email)
    if user is None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="No account has this email address. They need an account first.",
        )

    members = await get_club_members(conn, club_id)
    if any(member.user_id == user.id for member in members):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"{user.name} already helps run this event",
        )

    await sql_give_user_access_to_club(conn, user.id, club_id, UserXClubRelation.COLLABORATOR)
    return ClubMembersResponse(data=await get_club_members(conn, club_id))


@router.delete("/clubs/{club_id}/members/{user_id}", response_model=ClubMembersResponse)
async def remove_member(
    conn: DbSession,
    club_id: ClubId,
    user_id: UserId,
    user: UserPublic = Depends(user_authenticated_for_club),
) -> ClubMembersResponse:
    """Remove an organizer from the event. The owner removes others; anyone can leave."""
    members = await get_club_members(conn, club_id)
    member = next((member for member in members if member.user_id == user_id), None)
    if member is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="This account doesn't help run the event"
        )

    if member.relation is UserXClubRelation.OWNER:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="The owner can't be removed from the event. Delete the event instead.",
        )

    is_owner = any(
        candidate.user_id == user.id and candidate.relation is UserXClubRelation.OWNER
        for candidate in members
    )
    if not is_owner and user.id != user_id:
        raise forbidden("Only the owner of this event can remove someone else")

    await sql_remove_user_from_club(conn, user_id, club_id)
    return ClubMembersResponse(data=await get_club_members(conn, club_id))
