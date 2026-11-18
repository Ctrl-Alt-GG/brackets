from datetime import datetime

from sqlalchemy import delete, exists, func, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from bracket import orm
from bracket.models.db.user import User, UserInDB, UserInsertable, UserPublic, UserToUpdate
from bracket.models.enums import UserAccountType
from bracket.utils.id_types import ClubId, TournamentId, UserId
from bracket.utils.security import normalize_email


async def lock_user(session: AsyncSession, user_id: UserId) -> bool:
    """
    Serialize the commands whose rules cover all events of an account, such as their names and
    how many there are. Take it after the lock of an event the command changes.
    """
    return (
        await session.scalar(
            select(orm.User.id).where(orm.User.id == user_id).with_for_update(key_share=True)
        )
    ) is not None


async def get_user_access_to_tournament(
    session: AsyncSession, tournament_id: TournamentId, user_id: UserId
) -> bool:
    query = (
        select(orm.UserXClub.id)
        .join(orm.Tournament, orm.Tournament.club_id == orm.UserXClub.club_id)
        .where(orm.UserXClub.user_id == user_id, orm.Tournament.id == tournament_id)
    )
    return bool(await session.scalar(select(query.exists())))


async def get_which_clubs_has_user_access_to(session: AsyncSession, user_id: UserId) -> set[ClubId]:
    return {
        ClubId(club_id)
        for club_id in await session.scalars(
            select(orm.UserXClub.club_id).where(orm.UserXClub.user_id == user_id)
        )
    }


async def get_user_access_to_club(session: AsyncSession, club_id: ClubId, user_id: UserId) -> bool:
    return bool(
        await session.scalar(
            select(
                exists().where(orm.UserXClub.user_id == user_id, orm.UserXClub.club_id == club_id)
            )
        )
    )


async def update_user(session: AsyncSession, user_id: UserId, user: UserToUpdate) -> None:
    entity = await session.get(orm.User, user_id)
    if entity is not None:
        entity.name = user.name
        entity.email = normalize_email(user.email)
        await session.flush()


async def update_user_account_type(
    session: AsyncSession, user_id: UserId, account_type: UserAccountType
) -> None:
    entity = await session.get(orm.User, user_id)
    if entity is not None:
        entity.account_type = account_type
        await session.flush()


async def update_user_password(session: AsyncSession, user_id: UserId, password_hash: str) -> None:
    entity = await session.get(orm.User, user_id)
    if entity is not None:
        entity.password_hash = password_hash
        await session.flush()


async def get_user_by_id(session: AsyncSession, user_id: UserId) -> UserPublic | None:
    entity = await session.scalar(
        select(orm.User).where(orm.User.id == user_id).execution_options(populate_existing=True)
    )
    return UserPublic.model_validate(entity) if entity is not None else None


async def create_user(session: AsyncSession, user: UserInsertable) -> User:
    entity = orm.User(
        password_hash=user.password_hash,
        name=user.name,
        email=normalize_email(user.email),
        created=user.created,
        account_type=user.account_type,
    )
    session.add(entity)
    await session.flush()
    return User.model_validate(entity)


async def delete_user(session: AsyncSession, user_id: UserId) -> None:
    await session.execute(delete(orm.User).where(orm.User.id == user_id))


async def check_whether_email_is_in_use(session: AsyncSession, email: str) -> bool:
    return bool(
        await session.scalar(
            select(exists().where(func.lower(orm.User.email) == normalize_email(email)))
        )
    )


async def get_user(session: AsyncSession, email: str) -> UserInDB | None:
    # An exact match on the unique `ix_users_email_lower` index. Never a pattern match such as
    # `ILIKE`: `%` and `_` are valid in emails, so `%@example.org` would match other accounts.
    entity = await session.scalar(
        select(orm.User)
        .where(func.lower(orm.User.email) == normalize_email(email))
        .execution_options(populate_existing=True)
    )
    return UserInDB.model_validate(entity) if entity is not None else None


async def get_user_in_db(session: AsyncSession, user_id: UserId) -> UserInDB | None:
    entity = await session.scalar(
        select(orm.User).where(orm.User.id == user_id).execution_options(populate_existing=True)
    )
    return UserInDB.model_validate(entity) if entity is not None else None


async def get_user_in_db_with_session(
    session: AsyncSession, user_id: UserId, session_id: str
) -> UserInDB | None:
    """The user a session belongs to, unless the session was ended by logging out."""
    entity = await session.scalar(
        select(orm.User)
        .where(
            orm.User.id == user_id,
            ~exists().where(orm.RevokedSession.session_id == session_id),
        )
        .execution_options(populate_existing=True)
    )
    return UserInDB.model_validate(entity) if entity is not None else None


async def revoke_session(session: AsyncSession, session_id: str, expires: datetime) -> None:
    """End a session. This is forgotten at `expires`, once the last of its tokens has expired."""
    await session.execute(delete(orm.RevokedSession).where(orm.RevokedSession.expires < func.now()))
    await session.execute(
        insert(orm.RevokedSession)
        .values(session_id=session_id, expires=expires)
        .on_conflict_do_nothing()
    )
