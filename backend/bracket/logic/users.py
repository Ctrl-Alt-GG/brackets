from sqlalchemy.ext.asyncio import AsyncSession

from bracket.logic.tournaments import TournamentUploads, delete_tournament_completely
from bracket.models.enums import UserXClubRelation
from bracket.sql.clubs import get_clubs_for_user_id, sql_delete_club
from bracket.sql.tournaments import sql_get_tournaments
from bracket.sql.users import delete_user
from bracket.utils.id_types import UserId


async def delete_user_and_owned_clubs(
    session: AsyncSession, user_id: UserId
) -> list[TournamentUploads]:
    """
    Delete the user with the events they own and the tournaments of those events.

    The events they only help run belong to someone else and stay; deleting the user ends their
    membership of them. Returns the logos of the deleted tournaments, which the caller discards
    once the deletion is committed.
    """
    uploads = []
    for club in await get_clubs_for_user_id(session, user_id, UserXClubRelation.OWNER):
        for tournament in await sql_get_tournaments(session, (club.id,)):
            uploads.append(await delete_tournament_completely(session, tournament.id))

        await sql_delete_club(session, club.id)

    await delete_user(session, user_id)
    return uploads
