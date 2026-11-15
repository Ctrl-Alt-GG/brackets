from sqlalchemy import String, cast, delete, func, or_, select, update
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from bracket import orm
from bracket.models.db.club import Club, ClubCreateBody, ClubMember, ClubUpdateBody
from bracket.models.db.user_x_club import UserXClubRelation
from bracket.utils.id_types import ClubId, UserId


async def lock_club(session: AsyncSession, club_id: ClubId) -> bool:
    """Serialize event membership changes before checking access or changing its owner."""
    return (
        await session.scalar(select(orm.Club.id).where(orm.Club.id == club_id).with_for_update())
    ) is not None


async def sql_give_user_access_to_club(
    session: AsyncSession,
    user_id: UserId,
    club_id: ClubId,
    relation: UserXClubRelation = UserXClubRelation.OWNER,
) -> None:
    await lock_club(session, club_id)
    session.add(orm.UserXClub(club_id=club_id, user_id=user_id, relation=relation))
    await session.flush()


async def sql_remove_user_from_club(
    session: AsyncSession, user_id: UserId, club_id: ClubId
) -> None:
    await lock_club(session, club_id)
    await session.execute(
        delete(orm.UserXClub).where(
            orm.UserXClub.club_id == club_id, orm.UserXClub.user_id == user_id
        )
    )


async def get_club_members(session: AsyncSession, club_id: ClubId) -> list[ClubMember]:
    results = await session.execute(
        select(orm.UserXClub.user_id, orm.User.name, orm.User.email, orm.UserXClub.relation)
        .join(orm.User, orm.User.id == orm.UserXClub.user_id)
        .where(orm.UserXClub.club_id == club_id)
        .order_by(
            (orm.UserXClub.relation == UserXClubRelation.OWNER).desc(),
            orm.User.name,
            orm.User.id,
        )
    )
    return [ClubMember.model_validate(result._mapping) for result in results]


async def create_club(session: AsyncSession, club: ClubCreateBody, user_id: UserId) -> Club:
    entity = orm.Club(name=club.name)
    session.add(entity)
    await session.flush()
    await sql_give_user_access_to_club(session, user_id, ClubId(entity.id))
    return Club.model_validate(entity)


async def sql_update_club(
    session: AsyncSession, club_id: ClubId, club: ClubUpdateBody
) -> Club | None:
    entity = await session.get(orm.Club, club_id)
    if entity is None:
        return None
    entity.name = club.name
    await session.flush()
    return Club.model_validate(entity)


async def sql_delete_club(session: AsyncSession, club_id: ClubId) -> None:
    await lock_club(session, club_id)
    await session.execute(delete(orm.Club).where(orm.Club.id == club_id))


async def get_clubs_for_user_id(
    session: AsyncSession, user_id: UserId, relation: UserXClubRelation | None = None
) -> list[Club]:
    """The events the user runs, or with `relation`, only those they own or only help with."""
    query = (
        select(orm.Club)
        .join(orm.UserXClub, orm.Club.id == orm.UserXClub.club_id)
        .where(orm.UserXClub.user_id == user_id)
        .order_by(orm.Club.name, orm.Club.id)
        .execution_options(populate_existing=True)
    )
    if relation is not None:
        query = query.where(orm.UserXClub.relation == relation)
    return [Club.model_validate(entity) for entity in await session.scalars(query)]


async def get_club_by_id(session: AsyncSession, club_id: ClubId) -> Club:
    entity = (
        await session.scalars(
            select(orm.Club).where(orm.Club.id == club_id).execution_options(populate_existing=True)
        )
    ).one()
    return Club.model_validate(entity)


async def get_clubs_by_name_or_id(session: AsyncSession, name_or_id: str) -> list[Club]:
    """The events with this id or, regardless of case, this name. Names can repeat."""
    name = name_or_id.strip()
    entities = await session.scalars(
        select(orm.Club)
        .where(
            or_(func.lower(orm.Club.name) == func.lower(name), cast(orm.Club.id, String) == name)
        )
        .order_by(orm.Club.id)
        .execution_options(populate_existing=True)
    )
    return [Club.model_validate(entity) for entity in entities]


async def sql_make_club_owner(session: AsyncSession, club_id: ClubId, user_id: UserId) -> None:
    """
    Make the user the owner of the event, also when they didn't help run it yet. The previous
    owner stays on as an organizer. Lock the event before either change, including when the
    command is run from the CLI.
    """
    if not await lock_club(session, club_id):
        raise ValueError("Event does not exist")
    await session.execute(
        update(orm.UserXClub)
        .where(
            orm.UserXClub.club_id == club_id,
            orm.UserXClub.relation == UserXClubRelation.OWNER,
            orm.UserXClub.user_id != user_id,
        )
        .values(relation=UserXClubRelation.COLLABORATOR)
    )
    await session.execute(
        insert(orm.UserXClub)
        .values(club_id=club_id, user_id=user_id, relation=UserXClubRelation.OWNER)
        .on_conflict_do_update(
            index_elements=[orm.UserXClub.club_id, orm.UserXClub.user_id],
            set_={"relation": UserXClubRelation.OWNER},
        )
    )
