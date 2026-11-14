from pydantic import TypeAdapter
from sqlalchemy import delete, select, update
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import joinedload

from bracket import orm
from bracket.models.db.stage_item_inputs import (
    StageItemInput,
    StageItemInputBase,
    StageItemInputCreateBody,
    StageItemInputCreateBodyFinal,
    StageItemInputCreateBodyTentative,
    StageItemInputUpdateBody,
    StageItemInputUpdateBodyFinal,
    StageItemInputUpdateBodyTentative,
)
from bracket.utils.id_types import RankingId, StageItemId, StageItemInputId, TeamId, TournamentId


async def get_stage_item_input_by_id(
    conn: AsyncSession, tournament_id: TournamentId, stage_item_input_id: StageItemInputId
) -> StageItemInput | None:
    entity = await conn.scalar(
        select(orm.StageItemInput)
        .where(
            orm.StageItemInput.id == stage_item_input_id,
            orm.StageItemInput.tournament_id == tournament_id,
        )
        .options(joinedload(orm.StageItemInput.team))
        .execution_options(populate_existing=True)
    )
    if entity is None:
        return None
    return TypeAdapter(StageItemInput).validate_python(entity, from_attributes=True)


async def get_stage_item_ids_by_ranking_id(
    conn: AsyncSession, tournament_id: TournamentId, ranking_id: RankingId
) -> list[StageItemId]:
    ids = await conn.scalars(
        select(orm.StageItem.id)
        .join(orm.Stage, orm.Stage.id == orm.StageItem.stage_id)
        .where(orm.StageItem.ranking_id == ranking_id, orm.Stage.tournament_id == tournament_id)
    )
    return [StageItemId(id_) for id_ in ids]


async def sql_set_team_id_for_stage_item_input(
    conn: AsyncSession,
    tournament_id: TournamentId,
    stage_item_input_id: StageItemInputId,
    team_id: TeamId | None,
) -> None:
    await conn.execute(
        update(orm.StageItemInput)
        .where(
            orm.StageItemInput.tournament_id == tournament_id,
            orm.StageItemInput.id == stage_item_input_id,
        )
        .values(team_id=team_id)
    )


async def sql_delete_stage_item_inputs(conn: AsyncSession, stage_item_id: StageItemId) -> None:
    """Delete these slots, emptying the downstream slots that took their winners."""
    await conn.execute(
        update(orm.StageItemInput)
        .where(orm.StageItemInput.winner_from_stage_item_id == stage_item_id)
        .values(team_id=None, winner_from_stage_item_id=None, winner_position=None)
    )
    await conn.execute(
        delete(orm.StageItemInput).where(orm.StageItemInput.stage_item_id == stage_item_id)
    )


async def sql_create_stage_item_input(
    conn: AsyncSession,
    tournament_id: TournamentId,
    stage_item_id: StageItemId,
    stage_item_input: StageItemInputCreateBody,
) -> StageItemInputBase:
    entity = orm.StageItemInput(
        slot=stage_item_input.slot,
        tournament_id=tournament_id,
        stage_item_id=stage_item_id,
        team_id=stage_item_input.team_id
        if isinstance(stage_item_input, StageItemInputCreateBodyFinal)
        else None,
        winner_from_stage_item_id=stage_item_input.winner_from_stage_item_id
        if isinstance(stage_item_input, StageItemInputCreateBodyTentative)
        else None,
        winner_position=stage_item_input.winner_position
        if isinstance(stage_item_input, StageItemInputCreateBodyTentative)
        else None,
    )
    conn.add(entity)
    await conn.flush()
    return StageItemInputBase.model_validate(entity)


async def sql_update_stage_item_input(
    conn: AsyncSession,
    tournament_id: TournamentId,
    stage_item_id: StageItemId,
    stage_item_input_id: StageItemInputId,
    body: StageItemInputUpdateBody,
) -> None:
    entity = await conn.scalar(
        select(orm.StageItemInput)
        .where(
            orm.StageItemInput.id == stage_item_input_id,
            orm.StageItemInput.tournament_id == tournament_id,
            orm.StageItemInput.stage_item_id == stage_item_id,
        )
        .execution_options(populate_existing=True)
    )
    if entity is not None:
        entity.team_id = body.team_id if isinstance(body, StageItemInputUpdateBodyFinal) else None
        entity.winner_from_stage_item_id = (
            body.winner_from_stage_item_id
            if isinstance(body, StageItemInputUpdateBodyTentative)
            else None
        )
        entity.winner_position = (
            body.winner_position if isinstance(body, StageItemInputUpdateBodyTentative) else None
        )
        await conn.flush()
