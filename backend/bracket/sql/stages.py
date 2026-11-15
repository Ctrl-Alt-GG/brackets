from collections.abc import Mapping

from sqlalchemy import delete, select, update
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import joinedload, selectinload
from sqlalchemy.sql.elements import ColumnElement

from bracket import orm
from bracket.logic.ranking.statistics import TeamTotals
from bracket.logic.ranking.team_totals import get_team_totals
from bracket.models.db.stage import Stage, StageUpdateBody
from bracket.models.db.stage_item_inputs import StageItemInputFinal
from bracket.models.db.util import StageWithStageItems
from bracket.utils.id_types import RoundId, StageId, StageItemId, TeamId, TournamentId


async def get_full_tournament_details(
    session: AsyncSession,
    tournament_id: TournamentId,
    round_id: RoundId | None = None,
    stage_id: StageId | None = None,
    stage_item_ids: set[StageItemId] | None = None,
    *,
    no_draft_rounds: bool = False,
    with_team_totals: bool = False,
) -> list[StageWithStageItems]:
    """Load a tournament's stage tree, optionally enriching its teams with published results."""
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
                selectinload(orm.StageItem.inputs).joinedload(orm.StageItemInput.team),
                round_loader.selectinload(orm.Round.matches).options(
                    joinedload(orm.Match.stage_item_input1).joinedload(orm.StageItemInput.team),
                    joinedload(orm.Match.stage_item_input2).joinedload(orm.StageItemInput.team),
                ),
            )
        )
        .execution_options(populate_existing=True)
    )
    if stage_id is not None:
        stmt = stmt.where(orm.Stage.id == stage_id)
    if stage_item_ids is not None:
        stmt = stmt.where(orm.Stage.stage_items.any(orm.StageItem.id.in_(stage_item_ids)))

    stages = [StageWithStageItems.model_validate(stage) for stage in await session.scalars(stmt)]
    if with_team_totals:
        await add_team_totals(session, tournament_id, stages)
    return stages


async def add_team_totals(
    session: AsyncSession,
    tournament_id: TournamentId,
    stages: list[StageWithStageItems],
    *,
    totals: Mapping[TeamId, TeamTotals] | None = None,
) -> None:
    # The slots of a stage item and those in its matches are separate copies.
    inputs = [
        input_
        for stage in stages
        for stage_item in stage.stage_items
        for input_ in (
            *stage_item.inputs,
            *(
                match_input
                for round_ in stage_item.rounds
                for match in round_.matches
                for match_input in (match.stage_item_input1, match.stage_item_input2)
            ),
        )
        if isinstance(input_, StageItemInputFinal)
    ]
    if not inputs:
        return

    if totals is None:
        totals = await get_team_totals(session, tournament_id)
    for input_ in inputs:
        input_.team = input_.team.model_copy(
            update=totals.get(input_.team_id, TeamTotals()).model_dump()
        )


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
