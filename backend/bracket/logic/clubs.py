"""
Events (clubs in the code), and who runs them.

The names of the events an organizer owns differ, and an account runs a limited number of events.
Both rules cover all of an account's events, so the commands that check them lock the account
(after the event they change, as `bracket.sql.clubs` orders locks): two of them can't both see a
name as free or the last place as open.
"""

from fastapi import HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from starlette import status

from bracket.logic.subscriptions import Limit, check_requirement
from bracket.models.db.club import Club, ClubCreateBody, ClubMember, ClubUpdateBody
from bracket.models.db.user import UserPublic
from bracket.models.enums import UserXClubRelation
from bracket.sql.clubs import (
    count_clubs_for_user_id,
    create_club,
    get_club_by_id,
    get_club_members,
    get_clubs_for_user_id,
    sql_give_user_access_to_club,
    sql_make_club_owner,
    sql_remove_user_from_club,
    sql_update_club,
)
from bracket.sql.users import get_user, lock_user
from bracket.utils.errors import forbidden
from bracket.utils.id_types import ClubId, UserId


async def name_is_taken(
    session: AsyncSession, user_id: UserId, name: str, club_id: ClubId | None = None
) -> bool:
    """
    The events an organizer owns have different names. Others may use the same ones, also the
    owners of events the organizer only helps with.
    """
    return any(
        club.name.casefold() == name.casefold() and club.id != club_id
        for club in await get_clubs_for_user_id(session, user_id, UserXClubRelation.OWNER)
    )


async def check_name_is_free(
    session: AsyncSession, user_id: UserId, name: str, club_id: ClubId | None = None
) -> None:
    if await name_is_taken(session, user_id, name, club_id):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="You already have an event with this name",
        )


async def check_user_owns_club(session: AsyncSession, club_id: ClubId, user_id: UserId) -> None:
    """Organizers who were added to help can't rename the event or manage who helps."""
    members = await get_club_members(session, club_id)
    if not any(
        member.user_id == user_id and member.relation is UserXClubRelation.OWNER
        for member in members
    ):
        raise forbidden("Only the owner of this event can do that")


async def create_owned_club(session: AsyncSession, body: ClubCreateBody, user: UserPublic) -> Club:
    await lock_user(session, user.id)
    check_requirement(Limit.CLUBS, await count_clubs_for_user_id(session, user.id), user)
    await check_name_is_free(session, user.id, body.name)
    return await create_club(session, body, user.id)


async def rename_club(
    session: AsyncSession, club_id: ClubId, body: ClubUpdateBody, owner: UserPublic
) -> Club | None:
    await lock_user(session, owner.id)
    await check_name_is_free(session, owner.id, body.name, club_id)
    return await sql_update_club(session, club_id, body)


async def transfer_club_ownership(
    session: AsyncSession, club_id: ClubId, new_owner_id: UserId
) -> list[ClubMember]:
    """
    Hand the event over to another of its organizers, for an owner who leaves the organizing
    team. The previous owner stays on as an organizer.
    """
    members = await get_club_members(session, club_id)
    new_owner = next((member for member in members if member.user_id == new_owner_id), None)
    if new_owner is None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Only an organizer of the event can become its owner. Add them first.",
        )
    if new_owner.relation is UserXClubRelation.OWNER:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail=f"{new_owner.name} owns it already"
        )

    await lock_user(session, new_owner.user_id)
    club = await get_club_by_id(session, club_id)
    if await name_is_taken(session, new_owner.user_id, club.name, club_id):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=(
                f"{new_owner.name} already owns an event called {club.name}. Rename one of them "
                "first."
            ),
        )

    await sql_make_club_owner(session, club_id, new_owner.user_id)
    return await get_club_members(session, club_id)


async def add_club_member(session: AsyncSession, club_id: ClubId, email: str) -> list[ClubMember]:
    """Let another account help run the event and its tournaments."""
    user = await get_user(session, email)
    if user is None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="No account has this email address. They need an account first.",
        )

    members = await get_club_members(session, club_id)
    if any(member.user_id == user.id for member in members):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"{user.name} already helps run this event",
        )

    await sql_give_user_access_to_club(session, user.id, club_id, UserXClubRelation.COLLABORATOR)
    return await get_club_members(session, club_id)


async def remove_club_member(
    session: AsyncSession, club_id: ClubId, user_id: UserId, acting_user: UserPublic
) -> list[ClubMember]:
    """Remove an organizer from the event. The owner removes others; anyone can leave."""
    members = await get_club_members(session, club_id)
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
        candidate.user_id == acting_user.id and candidate.relation is UserXClubRelation.OWNER
        for candidate in members
    )
    if not is_owner and acting_user.id != user_id:
        raise forbidden("Only the owner of this event can remove someone else")

    await sql_remove_user_from_club(session, user_id, club_id)
    return await get_club_members(session, club_id)
