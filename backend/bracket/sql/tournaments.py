from typing import Literal

from sqlalchemy import Select, String, cast, delete, exists, func, or_, select, update
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import aliased, with_expression
from sqlalchemy.sql.elements import ColumnElement

from bracket import orm
from bracket.models.db.tournament import Tournament, TournamentBody
from bracket.models.enums import StageType, TournamentStatus
from bracket.utils.id_types import TournamentId, UserId

TournamentFilter = Literal["ALL", "OPEN", "ARCHIVED"]
# The records a tournament has, which limits count.
TournamentRecord = (
    type[orm.Stage]
    | type[orm.StageItem]
    | type[orm.Round]
    | type[orm.TournamentTeam]
    | type[orm.TournamentPlayer]
    | type[orm.Ranking]
)


def with_progress(stmt: Select[orm.Tournament]) -> Select[orm.Tournament]:
    """Attach published match progress and whether a Swiss stage can still add rounds."""
    played = or_(
        orm.Match.stage_item_input1_score != 0,
        orm.Match.stage_item_input2_score != 0,
        orm.Match.scoreless_result,
    )
    progress = (
        select(
            orm.Stage.tournament_id,
            func.count().label("matches_total"),
            func.count().filter(played).label("matches_played"),
            func.max(
                orm.Match.start_time
                + func.make_interval(
                    0, 0, 0, 0, 0, orm.Match.duration_minutes + orm.Match.margin_minutes
                )
            ).label("last_match_end"),
        )
        .select_from(orm.Match)
        .join(orm.Round)
        .join(orm.StageItem)
        .join(orm.Stage)
        .where(orm.Round.is_draft.is_(False))
        .group_by(orm.Stage.tournament_id)
        .subquery()
    )
    active_stage = aliased(orm.Stage)
    active_id = (
        select(active_stage.id)
        .where(
            active_stage.tournament_id == orm.Tournament.id,
            active_stage.is_active,
        )
        .correlate(orm.Tournament)
        .scalar_subquery()
    )
    more_rounds = (
        exists()
        .where(
            orm.StageItem.stage_id == orm.Stage.id,
            orm.Stage.tournament_id == orm.Tournament.id,
            orm.StageItem.type == StageType.SWISS,
            orm.Stage.id >= func.coalesce(active_id, 0),
        )
        .correlate(orm.Tournament)
    )
    return (
        stmt.outerjoin(progress, progress.c.tournament_id == orm.Tournament.id)
        .options(
            with_expression(
                orm.Tournament.matches_total, func.coalesce(progress.c.matches_total, 0)
            ),
            with_expression(
                orm.Tournament.matches_played, func.coalesce(progress.c.matches_played, 0)
            ),
            with_expression(orm.Tournament.last_match_end, progress.c.last_match_end),
            with_expression(orm.Tournament.more_rounds_possible, more_rounds),
        )
        .execution_options(populate_existing=True)
    )


async def lock_tournament(session: AsyncSession, tournament_id: TournamentId) -> bool:
    """
    Serialize the commands of a tournament. Whether a slot is unused and assigning its replacement
    can't interleave with a score being recorded, for example. `False` when it doesn't exist.
    """
    return (
        await session.scalar(
            select(orm.Tournament.id).where(orm.Tournament.id == tournament_id).with_for_update()
        )
    ) is not None


async def count_tournament_records(
    session: AsyncSession, record: TournamentRecord, tournament_id: TournamentId
) -> int:
    return int(
        await session.scalar(
            select(func.count()).select_from(record).where(record.tournament_id == tournament_id)
        )
        or 0
    )


async def sql_get_tournament(session: AsyncSession, tournament_id: TournamentId) -> Tournament:
    entity = (
        await session.scalars(
            with_progress(select(orm.Tournament).where(orm.Tournament.id == tournament_id))
        )
    ).one()
    return Tournament.model_validate(entity)


async def sql_get_tournament_by_endpoint_name(
    session: AsyncSession, endpoint_name: str
) -> Tournament | None:
    entity = await session.scalar(
        with_progress(
            select(orm.Tournament).where(
                func.lower(orm.Tournament.dashboard_endpoint) == endpoint_name.lower(),
                orm.Tournament.dashboard_public.is_(True),
            )
        )
    )
    return Tournament.model_validate(entity) if entity is not None else None


async def _get_tournaments_where(
    session: AsyncSession, condition: ColumnElement[bool], filter_: TournamentFilter
) -> list[Tournament]:
    stmt = select(orm.Tournament).where(condition)
    if filter_ != "ALL":
        stmt = stmt.where(orm.Tournament.status == TournamentStatus(filter_))
    stmt = with_progress(stmt).order_by(
        orm.Tournament.status == TournamentStatus.ARCHIVED,
        orm.Tournament.start_time.desc(),
        orm.Tournament.id,
    )
    return [Tournament.model_validate(entity) for entity in await session.scalars(stmt)]


async def sql_get_visible_tournaments(
    session: AsyncSession, user_id: UserId | None, filter_: TournamentFilter = "OPEN"
) -> list[Tournament]:
    """The tournaments that everyone may see, and those that the user runs."""
    visible = or_(orm.Tournament.status == TournamentStatus.OPEN, orm.Tournament.dashboard_public)
    if user_id is not None:
        visible = or_(
            visible,
            orm.Tournament.id.in_(
                select(orm.TournamentOrganizer.tournament_id).where(
                    orm.TournamentOrganizer.user_id == user_id
                )
            ),
        )
    return await _get_tournaments_where(session, visible, filter_)


async def get_tournaments_by_name_or_id(session: AsyncSession, name_or_id: str) -> list[Tournament]:
    """The tournaments with this id or, regardless of case, this name. Names can repeat."""
    name = name_or_id.strip()
    return await _get_tournaments_where(
        session,
        or_(
            func.lower(orm.Tournament.name) == func.lower(name),
            cast(orm.Tournament.id, String) == name,
        ),
        "ALL",
    )


async def sql_delete_tournament(session: AsyncSession, tournament_id: TournamentId) -> None:
    """
    Delete the tournament with everything in it. Its teams and players stay: they only stop
    taking part in it.
    """
    # Match-to-slot and slot-to-team foreign keys deliberately refuse destructive deletions.
    # Remove matches before stages, then let the database cascade the remaining descendants.
    await session.execute(delete(orm.Match).where(orm.Match.tournament_id == tournament_id))
    await session.execute(delete(orm.Stage).where(orm.Stage.tournament_id == tournament_id))
    await session.execute(delete(orm.Tournament).where(orm.Tournament.id == tournament_id))


async def sql_update_tournament(
    session: AsyncSession, tournament_id: TournamentId, tournament: TournamentBody
) -> None:
    entity = await session.get(orm.Tournament, tournament_id)
    if entity is not None:
        entity.name = tournament.name
        entity.start_time = tournament.start_time
        entity.dashboard_public = tournament.dashboard_public
        entity.dashboard_endpoint = tournament.dashboard_endpoint
        entity.duration_minutes = tournament.duration_minutes
        entity.margin_minutes = tournament.margin_minutes
        await session.flush()


async def sql_update_tournament_logo(
    session: AsyncSession, tournament_id: TournamentId, logo_path: str | None
) -> None:
    entity = await session.get(orm.Tournament, tournament_id)
    if entity is not None:
        entity.logo_path = logo_path
        await session.flush()


async def sql_move_tournament_start(
    session: AsyncSession, tournament_id: TournamentId, minutes: int
) -> None:
    await session.execute(
        update(orm.Tournament)
        .where(orm.Tournament.id == tournament_id)
        .values(start_time=orm.Tournament.start_time + func.make_interval(0, 0, 0, 0, 0, minutes))
        .execution_options(synchronize_session=False)
    )


async def sql_update_tournament_status(
    session: AsyncSession, tournament_id: TournamentId, status: TournamentStatus
) -> None:
    entity = await session.get(orm.Tournament, tournament_id)
    if entity is not None:
        entity.status = status
        await session.flush()


async def sql_create_tournament(session: AsyncSession, tournament: TournamentBody) -> TournamentId:
    entity = orm.Tournament(**tournament.model_dump())
    session.add(entity)
    await session.flush()
    return TournamentId(entity.id)
