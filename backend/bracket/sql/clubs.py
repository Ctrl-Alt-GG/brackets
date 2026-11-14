from sqlalchemy import String, cast, delete, func, or_, select, update
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from bracket import orm
from bracket.models.db.club import Club, ClubCreateBody, ClubMember, ClubUpdateBody
from bracket.models.db.user_x_club import UserXClubRelation
from bracket.utils.id_types import ClubId, UserId


async def sql_give_user_access_to_club(
    conn: AsyncSession,
    user_id: UserId,
    club_id: ClubId,
    relation: UserXClubRelation = UserXClubRelation.OWNER,
) -> None:
    conn.add(orm.UserXClub(club_id=club_id, user_id=user_id, relation=relation))
    await conn.flush()


async def sql_remove_user_from_club(conn: AsyncSession, user_id: UserId, club_id: ClubId) -> None:
    await conn.execute(
        delete(orm.UserXClub).where(
            orm.UserXClub.club_id == club_id, orm.UserXClub.user_id == user_id
        )
    )


async def get_club_members(conn: AsyncSession, club_id: ClubId) -> list[ClubMember]:
    results = await conn.execute(
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


async def create_club(conn: AsyncSession, club: ClubCreateBody, user_id: UserId) -> Club:
    entity = orm.Club(name=club.name)
    conn.add(entity)
    await conn.flush()
    await sql_give_user_access_to_club(conn, user_id, ClubId(entity.id))
    return Club.model_validate(entity)


async def sql_update_club(conn: AsyncSession, club_id: ClubId, club: ClubUpdateBody) -> Club | None:
    entity = await conn.get(orm.Club, club_id)
    if entity is None:
        return None
    entity.name = club.name
    await conn.flush()
    return Club.model_validate(entity)


async def sql_delete_club(conn: AsyncSession, club_id: ClubId) -> None:
    await conn.execute(delete(orm.Club).where(orm.Club.id == club_id))


async def get_clubs_for_user_id(
    conn: AsyncSession, user_id: UserId, relation: UserXClubRelation | None = None
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
    return [Club.model_validate(entity) for entity in await conn.scalars(query)]


async def get_club_by_id(conn: AsyncSession, club_id: ClubId) -> Club:
    entity = (
        await conn.scalars(
            select(orm.Club).where(orm.Club.id == club_id).execution_options(populate_existing=True)
        )
    ).one()
    return Club.model_validate(entity)


async def get_clubs_by_name_or_id(conn: AsyncSession, name_or_id: str) -> list[Club]:
    """The events with this id or, regardless of case, this name. Names can repeat."""
    name = name_or_id.strip()
    entities = await conn.scalars(
        select(orm.Club)
        .where(
            or_(func.lower(orm.Club.name) == func.lower(name), cast(orm.Club.id, String) == name)
        )
        .order_by(orm.Club.id)
        .execution_options(populate_existing=True)
    )
    return [Club.model_validate(entity) for entity in entities]


async def sql_make_club_owner(conn: AsyncSession, club_id: ClubId, user_id: UserId) -> None:
    """
    Make the user the owner of the event, also when they didn't help run it yet. The previous
    owner stays on as an organizer. Both happen in the caller's transaction, so the event never
    has two owners or none.
    """
    await conn.execute(
        update(orm.UserXClub)
        .where(
            orm.UserXClub.club_id == club_id,
            orm.UserXClub.relation == UserXClubRelation.OWNER,
            orm.UserXClub.user_id != user_id,
        )
        .values(relation=UserXClubRelation.COLLABORATOR)
    )
    await conn.execute(
        insert(orm.UserXClub)
        .values(club_id=club_id, user_id=user_id, relation=UserXClubRelation.OWNER)
        .on_conflict_do_update(
            index_elements=[orm.UserXClub.club_id, orm.UserXClub.user_id],
            set_={"relation": UserXClubRelation.OWNER},
        )
    )
