"""
Who runs a tournament: its owner, and the accounts the owner added to help.

Changing who runs a tournament is a command on it, which holds the tournament's lock (see
`bracket.routes.access`). A command that was let in finishes before someone loses access, and one
that waits for the tournament sees its organizers as they are after the change.
"""

from sqlalchemy import delete, exists, func, select, update
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from bracket import orm
from bracket.models.db.organizer import Organizer
from bracket.models.enums import TournamentRole
from bracket.utils.id_types import TournamentId, UserId


async def get_organizers(session: AsyncSession, tournament_id: TournamentId) -> list[Organizer]:
    """The owner first, then the others by name."""
    results = await session.execute(
        select(
            orm.TournamentOrganizer.user_id,
            orm.User.name,
            orm.User.email,
            orm.TournamentOrganizer.role,
        )
        .join(orm.User, orm.User.id == orm.TournamentOrganizer.user_id)
        .where(orm.TournamentOrganizer.tournament_id == tournament_id)
        .order_by(
            (orm.TournamentOrganizer.role == TournamentRole.OWNER).desc(),
            orm.User.name,
            orm.User.id,
        )
    )
    return [Organizer.model_validate(result._mapping) for result in results]


async def get_role(
    session: AsyncSession, tournament_id: TournamentId, user_id: UserId
) -> TournamentRole | None:
    """How the user runs the tournament, or `None` when they don't."""
    return await session.scalar(
        select(orm.TournamentOrganizer.role).where(
            orm.TournamentOrganizer.tournament_id == tournament_id,
            orm.TournamentOrganizer.user_id == user_id,
        )
    )


async def is_organizer(session: AsyncSession, tournament_id: TournamentId, user_id: UserId) -> bool:
    return bool(
        await session.scalar(
            select(
                exists().where(
                    orm.TournamentOrganizer.tournament_id == tournament_id,
                    orm.TournamentOrganizer.user_id == user_id,
                )
            )
        )
    )


async def get_organized_tournament_ids(session: AsyncSession, user_id: UserId) -> set[TournamentId]:
    return {
        TournamentId(tournament_id)
        for tournament_id in await session.scalars(
            select(orm.TournamentOrganizer.tournament_id).where(
                orm.TournamentOrganizer.user_id == user_id
            )
        )
    }


async def count_owned_tournaments(session: AsyncSession, user_id: UserId) -> int:
    return int(
        await session.scalar(
            select(func.count())
            .select_from(orm.TournamentOrganizer)
            .where(
                orm.TournamentOrganizer.user_id == user_id,
                orm.TournamentOrganizer.role == TournamentRole.OWNER,
            )
        )
        or 0
    )


async def sql_add_organizer(
    session: AsyncSession, tournament_id: TournamentId, user_id: UserId, role: TournamentRole
) -> None:
    session.add(orm.TournamentOrganizer(tournament_id=tournament_id, user_id=user_id, role=role))
    await session.flush()


async def sql_remove_organizer(
    session: AsyncSession, tournament_id: TournamentId, user_id: UserId
) -> None:
    await session.execute(
        delete(orm.TournamentOrganizer).where(
            orm.TournamentOrganizer.tournament_id == tournament_id,
            orm.TournamentOrganizer.user_id == user_id,
        )
    )


async def sql_make_owner(
    session: AsyncSession, tournament_id: TournamentId, user_id: UserId
) -> None:
    """
    Make the user the owner of the tournament, also when they didn't help run it yet. The previous
    owner stays on as an organizer. The caller holds the tournament's lock.
    """
    await session.execute(
        update(orm.TournamentOrganizer)
        .where(
            orm.TournamentOrganizer.tournament_id == tournament_id,
            orm.TournamentOrganizer.role == TournamentRole.OWNER,
            orm.TournamentOrganizer.user_id != user_id,
        )
        .values(role=TournamentRole.COLLABORATOR)
    )
    await session.execute(
        insert(orm.TournamentOrganizer)
        .values(tournament_id=tournament_id, user_id=user_id, role=TournamentRole.OWNER)
        .on_conflict_do_update(
            index_elements=[
                orm.TournamentOrganizer.tournament_id,
                orm.TournamentOrganizer.user_id,
            ],
            set_={"role": TournamentRole.OWNER},
        )
    )
