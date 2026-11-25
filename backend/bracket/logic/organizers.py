"""
Who runs a tournament: its owner, and the accounts the owner added to help.

Everyone who runs a tournament can manage it. Only the owner decides who helps, hands the
tournament over and deletes it; anyone who helps can leave.
"""

from fastapi import HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from starlette import status

from bracket.models.db.organizer import Organizer
from bracket.models.db.user import UserPublic
from bracket.models.enums import TournamentRole
from bracket.sql.organizers import (
    get_organizers,
    get_role,
    sql_add_organizer,
    sql_make_owner,
    sql_remove_organizer,
)
from bracket.sql.users import get_user
from bracket.utils.errors import forbidden
from bracket.utils.i18n import gettext
from bracket.utils.id_types import TournamentId, UserId


async def check_user_owns_tournament(
    session: AsyncSession, tournament_id: TournamentId, user_id: UserId
) -> None:
    if await get_role(session, tournament_id, user_id) is not TournamentRole.OWNER:
        raise forbidden(gettext("Only the owner of this tournament can do that"))


async def add_organizer(
    session: AsyncSession, tournament_id: TournamentId, email: str
) -> list[Organizer]:
    """Let another account help run the tournament, so that organizers don't share a login."""
    user = await get_user(session, email)
    if user is None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=gettext("No account has this email address. They need an account first."),
        )
    if await get_role(session, tournament_id, user.id) is not None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=gettext("{name} already helps run this tournament", name=user.name),
        )

    await sql_add_organizer(session, tournament_id, user.id, TournamentRole.COLLABORATOR)
    return await get_organizers(session, tournament_id)


async def remove_organizer(
    session: AsyncSession, tournament_id: TournamentId, user_id: UserId, acting_user: UserPublic
) -> list[Organizer]:
    """Remove an organizer from the tournament. The owner removes others; anyone can leave."""
    organizers = await get_organizers(session, tournament_id)
    organizer = next((organizer for organizer in organizers if organizer.user_id == user_id), None)
    if organizer is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=gettext("This account doesn't help run the tournament"),
        )
    if organizer.role is TournamentRole.OWNER:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=gettext(
                "The owner can't leave the tournament. Make someone else the owner first."
            ),
        )

    acting_user_owns = any(
        candidate.user_id == acting_user.id and candidate.role is TournamentRole.OWNER
        for candidate in organizers
    )
    if not acting_user_owns and acting_user.id != user_id:
        raise forbidden(gettext("Only the owner of this tournament can remove someone else"))

    await sql_remove_organizer(session, tournament_id, user_id)
    return await get_organizers(session, tournament_id)


async def transfer_ownership(
    session: AsyncSession, tournament_id: TournamentId, new_owner_id: UserId
) -> list[Organizer]:
    """
    Hand the tournament over to another of its organizers, for an owner who leaves the organizing
    team. The previous owner stays on as an organizer.
    """
    organizers = await get_organizers(session, tournament_id)
    new_owner = next(
        (organizer for organizer in organizers if organizer.user_id == new_owner_id), None
    )
    if new_owner is None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=gettext(
                "Only an organizer of the tournament can become its owner. Add them first."
            ),
        )
    if new_owner.role is TournamentRole.OWNER:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=gettext("{name} owns it already", name=new_owner.name),
        )

    await sql_make_owner(session, tournament_id, new_owner_id)
    return await get_organizers(session, tournament_id)
