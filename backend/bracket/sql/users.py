from datetime import datetime

from sqlalchemy import delete, exists, func, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from bracket import orm
from bracket.logic.tournaments import TournamentUploads, sql_delete_tournament_completely
from bracket.models.db.account import UserAccountType
from bracket.models.db.user import User, UserInDB, UserInsertable, UserPublic, UserToUpdate
from bracket.models.db.user_x_club import UserXClubRelation
from bracket.sql.clubs import get_clubs_for_user_id, sql_delete_club
from bracket.sql.tournaments import sql_get_tournaments
from bracket.utils.id_types import ClubId, TournamentId, UserId
from bracket.utils.security import normalize_email


async def get_user_access_to_tournament(
    conn: AsyncSession, tournament_id: TournamentId, user_id: UserId
) -> bool:
    query = (
        select(orm.UserXClub.id)
        .join(orm.Tournament, orm.Tournament.club_id == orm.UserXClub.club_id)
        .where(orm.UserXClub.user_id == user_id, orm.Tournament.id == tournament_id)
    )
    return bool(await conn.scalar(select(query.exists())))


async def get_which_clubs_has_user_access_to(conn: AsyncSession, user_id: UserId) -> set[ClubId]:
    return {
        ClubId(club_id)
        for club_id in await conn.scalars(
            select(orm.UserXClub.club_id).where(orm.UserXClub.user_id == user_id)
        )
    }


async def get_user_access_to_club(conn: AsyncSession, club_id: ClubId, user_id: UserId) -> bool:
    return bool(
        await conn.scalar(
            select(
                exists().where(orm.UserXClub.user_id == user_id, orm.UserXClub.club_id == club_id)
            )
        )
    )


async def update_user(conn: AsyncSession, user_id: UserId, user: UserToUpdate) -> None:
    entity = await conn.get(orm.User, user_id)
    if entity is not None:
        entity.name = user.name
        entity.email = normalize_email(user.email)
        await conn.flush()


async def update_user_account_type(
    conn: AsyncSession, user_id: UserId, account_type: UserAccountType
) -> None:
    entity = await conn.get(orm.User, user_id)
    if entity is not None:
        entity.account_type = account_type
        await conn.flush()


async def update_user_password(conn: AsyncSession, user_id: UserId, password_hash: str) -> None:
    entity = await conn.get(orm.User, user_id)
    if entity is not None:
        entity.password_hash = password_hash
        await conn.flush()


async def get_user_by_id(conn: AsyncSession, user_id: UserId) -> UserPublic | None:
    entity = await conn.scalar(
        select(orm.User).where(orm.User.id == user_id).execution_options(populate_existing=True)
    )
    return UserPublic.model_validate(entity) if entity is not None else None


async def create_user(conn: AsyncSession, user: UserInsertable) -> User:
    entity = orm.User(
        password_hash=user.password_hash,
        name=user.name,
        email=normalize_email(user.email),
        created=user.created,
        account_type=user.account_type,
    )
    conn.add(entity)
    await conn.flush()
    return User.model_validate(entity)


async def delete_user(conn: AsyncSession, user_id: UserId) -> None:
    await conn.execute(delete(orm.User).where(orm.User.id == user_id))


async def check_whether_email_is_in_use(conn: AsyncSession, email: str) -> bool:
    return bool(
        await conn.scalar(
            select(exists().where(func.lower(orm.User.email) == normalize_email(email)))
        )
    )


async def get_user(conn: AsyncSession, email: str) -> UserInDB | None:
    # An exact match on the unique `ix_users_email_lower` index. Never a pattern match such as
    # `ILIKE`: `%` and `_` are valid in emails, so `%@example.org` would match other accounts.
    entity = await conn.scalar(
        select(orm.User)
        .where(func.lower(orm.User.email) == normalize_email(email))
        .execution_options(populate_existing=True)
    )
    return UserInDB.model_validate(entity) if entity is not None else None


async def get_user_in_db(conn: AsyncSession, user_id: UserId) -> UserInDB | None:
    entity = await conn.scalar(
        select(orm.User).where(orm.User.id == user_id).execution_options(populate_existing=True)
    )
    return UserInDB.model_validate(entity) if entity is not None else None


async def get_user_in_db_with_session(
    conn: AsyncSession, user_id: UserId, session_id: str
) -> UserInDB | None:
    """The user a session belongs to, unless the session was ended by logging out."""
    entity = await conn.scalar(
        select(orm.User)
        .where(
            orm.User.id == user_id,
            ~exists().where(orm.RevokedSession.session_id == session_id),
        )
        .execution_options(populate_existing=True)
    )
    return UserInDB.model_validate(entity) if entity is not None else None


async def revoke_session(conn: AsyncSession, session_id: str, expires: datetime) -> None:
    """End a session. This is forgotten at `expires`, once the last of its tokens has expired."""
    await conn.execute(delete(orm.RevokedSession).where(orm.RevokedSession.expires < func.now()))
    await conn.execute(
        insert(orm.RevokedSession)
        .values(session_id=session_id, expires=expires)
        .on_conflict_do_nothing()
    )


async def delete_user_and_owned_clubs(
    conn: AsyncSession, user_id: UserId
) -> list[TournamentUploads]:
    """
    Delete the user with the events they own and the tournaments of those events.

    The events they only help run belong to someone else and stay; deleting the user ends their
    membership of them. Returns the logos of the deleted tournaments, which the caller discards
    once the deletion is committed.
    """
    uploads = []
    for club in await get_clubs_for_user_id(conn, user_id, UserXClubRelation.OWNER):
        for tournament in await sql_get_tournaments(conn, (club.id,)):
            uploads.append(await sql_delete_tournament_completely(conn, tournament.id))

        await sql_delete_club(conn, club.id)

    await delete_user(conn, user_id)
    return uploads
