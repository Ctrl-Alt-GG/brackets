"""
Events, called clubs in the code, and who runs them.

Commands that involve an event lock its row first, before the rows of its tournaments or of
accounts, in these strengths:

- Changing who runs an event, or the event itself: `lock_club`, which excludes every other lock.
- Creating a tournament: `lock_club_for_new_tournament`. It serializes creations, so that two of
  them can't both take the last place the limit allows, and waits for membership changes.
- Any command on one of its tournaments: `lock_club_of_tournament`, which only excludes
  `lock_club`. A command that was let in finishes before someone loses access, and one that waits
  for the event sees the membership as it is after the change.
"""

from sqlalchemy import String, cast, delete, func, or_, select, update
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from bracket import orm
from bracket.models.db.club import Club, ClubCreateBody, ClubMember, ClubUpdateBody
from bracket.models.enums import UserXClubRelation
from bracket.utils.id_types import ClubId, TournamentId, UserId


async def lock_club(session: AsyncSession, club_id: ClubId) -> bool:
    """Lock the event against every other command on it. `False` when it doesn't exist."""
    return (
        await session.scalar(select(orm.Club.id).where(orm.Club.id == club_id).with_for_update())
    ) is not None


async def lock_club_for_new_tournament(session: AsyncSession, club_id: ClubId) -> bool:
    return (
        await session.scalar(
            select(orm.Club.id).where(orm.Club.id == club_id).with_for_update(key_share=True)
        )
    ) is not None


async def lock_club_of_tournament(session: AsyncSession, tournament_id: TournamentId) -> bool:
    """`False` when the tournament doesn't exist."""
    return (
        await session.scalar(
            select(orm.Club.id)
            .join(orm.Tournament, orm.Tournament.club_id == orm.Club.id)
            .where(orm.Tournament.id == tournament_id)
            .with_for_update(read=True, key_share=True, of=orm.Club)
        )
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


async def count_clubs_for_user_id(session: AsyncSession, user_id: UserId) -> int:
    """How many events the user runs, as their owner or helping."""
    return int(
        await session.scalar(
            select(func.count()).select_from(orm.UserXClub).where(orm.UserXClub.user_id == user_id)
        )
        or 0
    )


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
