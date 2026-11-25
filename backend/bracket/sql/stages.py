from sqlalchemy import delete, select, update
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import joinedload, selectinload
from sqlalchemy.sql.elements import ColumnElement

from bracket import orm
from bracket.models.db.stage import Stage, StageUpdateBody
from bracket.models.db.stage_tree import StageWithStageItems
from bracket.utils.id_types import RoundId, StageId, StageItemId, TournamentId

# Loads a slot's team: its participation in the tournament, with the team itself.
SLOT_TEAM = joinedload(orm.StageItemInput.team).joinedload(orm.TournamentTeam.team)


async def get_full_tournament_details(
    session: AsyncSession,
    tournament_id: TournamentId,
    round_id: RoundId | None = None,
    stage_id: StageId | None = None,
    stage_item_ids: set[StageItemId] | None = None,
    *,
    no_draft_rounds: bool = False,
) -> list[StageWithStageItems]:
    """
    Load a tournament's stage tree. Its teams carry the results of a team that hasn't played:
    `bracket.logic.ranking.team_totals` replaces them for answers that show them.
    """
    item_loader = selectinload(orm.Stage.stage_items)
    if stage_item_ids is not None:
        item_loader = selectinload(orm.Stage.stage_items.and_(orm.StageItem.id.in_(stage_item_ids)))

    round_criteria: list[ColumnElement[bool]] = []
    if no_draft_rounds:
        round_criteria.append(orm.Round.is_draft.is_(False))
    if round_id is not None:
        round_criteria.append(orm.Round.id == round_id)
    round_loader = selectinload(orm.StageItem.rounds)
    if round_criteria:
        round_loader = selectinload(orm.StageItem.rounds.and_(*round_criteria))

    stmt = (
        select(orm.Stage)
        .where(orm.Stage.tournament_id == tournament_id)
        .order_by(orm.Stage.id)
        .options(
            item_loader.options(
                selectinload(orm.StageItem.inputs).options(SLOT_TEAM),
                round_loader.selectinload(orm.Round.matches).options(
                    joinedload(orm.Match.stage_item_input1).options(SLOT_TEAM),
                    joinedload(orm.Match.stage_item_input2).options(SLOT_TEAM),
                ),
            )
        )
        .execution_options(populate_existing=True)
    )
    if stage_id is not None:
        stmt = stmt.where(orm.Stage.id == stage_id)
    if stage_item_ids is not None:
        stmt = stmt.where(orm.Stage.stage_items.any(orm.StageItem.id.in_(stage_item_ids)))

    return [StageWithStageItems.model_validate(stage) for stage in await session.scalars(stmt)]


async def sql_delete_stage(
    session: AsyncSession, tournament_id: TournamentId, stage_id: StageId
) -> None:
    await session.execute(
        delete(orm.Stage).where(orm.Stage.id == stage_id, orm.Stage.tournament_id == tournament_id)
    )


async def sql_create_stage(session: AsyncSession, tournament_id: TournamentId) -> Stage:
    stage = orm.Stage(name="Stage", tournament_id=tournament_id, is_active=False)
    session.add(stage)
    await session.flush()
    return Stage.model_validate(stage)


async def sql_update_stage(
    session: AsyncSession,
    tournament_id: TournamentId,
    stage_id: StageId,
    body: StageUpdateBody,
) -> None:
    stage = await session.scalar(
        select(orm.Stage).where(orm.Stage.id == stage_id, orm.Stage.tournament_id == tournament_id)
    )
    if stage is not None:
        stage.name = body.name
        stage.custom_duration_minutes = body.custom_duration_minutes
        await session.flush()


async def sql_activate_next_stage(
    session: AsyncSession, new_active_stage_id: StageId, tournament_id: TournamentId
) -> None:
    await session.execute(
        update(orm.Stage)
        .where(orm.Stage.tournament_id == tournament_id)
        .values(is_active=orm.Stage.id == new_active_stage_id)
    )
