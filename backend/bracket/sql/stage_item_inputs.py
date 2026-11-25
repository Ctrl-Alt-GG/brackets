from collections.abc import Mapping, Sequence

from pydantic import TypeAdapter
from sqlalchemy import delete, select, update
from sqlalchemy.ext.asyncio import AsyncSession

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
from bracket.models.results import TeamStatistics
from bracket.sql.stages import SLOT_TEAM
from bracket.utils.id_types import StageItemId, StageItemInputId, TeamId, TournamentId


async def get_stage_item_input_by_id(
    session: AsyncSession, tournament_id: TournamentId, stage_item_input_id: StageItemInputId
) -> StageItemInput | None:
    entity = await session.scalar(
        select(orm.StageItemInput)
        .where(
            orm.StageItemInput.id == stage_item_input_id,
            orm.StageItemInput.tournament_id == tournament_id,
        )
        .options(SLOT_TEAM)
        .execution_options(populate_existing=True)
    )
    if entity is None:
        return None
    return TypeAdapter(StageItemInput).validate_python(entity, from_attributes=True)


async def update_stage_item_input_statistics(
    session: AsyncSession,
    tournament_id: TournamentId,
    statistics: Mapping[StageItemInputId, TeamStatistics],
) -> None:
    """Store the results of these slots, in one round trip to the database."""
    if not statistics:
        return
    await session.execute(
        update(orm.StageItemInput)
        .where(orm.StageItemInput.tournament_id == tournament_id)
        .execution_options(synchronize_session=False),
        [
            {
                "id": stage_item_input_id,
                "wins": input_statistics.wins,
                "draws": input_statistics.draws,
                "losses": input_statistics.losses,
                "points": input_statistics.points,
            }
            for stage_item_input_id, input_statistics in statistics.items()
        ],
    )


async def sql_set_team_id_for_stage_item_input(
    session: AsyncSession,
    tournament_id: TournamentId,
    stage_item_input_id: StageItemInputId,
    team_id: TeamId | None,
) -> None:
    await session.execute(
        update(orm.StageItemInput)
        .where(
            orm.StageItemInput.tournament_id == tournament_id,
            orm.StageItemInput.id == stage_item_input_id,
        )
        .values(team_id=team_id)
    )


async def sql_delete_stage_item_inputs(session: AsyncSession, stage_item_id: StageItemId) -> None:
    """Delete these slots, emptying the downstream slots that took their winners."""
    await session.execute(
        update(orm.StageItemInput)
        .where(orm.StageItemInput.winner_from_stage_item_id == stage_item_id)
        .values(team_id=None, winner_from_stage_item_id=None, winner_position=None)
    )
    await session.execute(
        delete(orm.StageItemInput).where(orm.StageItemInput.stage_item_id == stage_item_id)
    )


async def sql_create_stage_item_inputs(
    session: AsyncSession,
    tournament_id: TournamentId,
    stage_item_id: StageItemId,
    inputs: Sequence[StageItemInputCreateBody],
) -> list[StageItemInputBase]:
    entities = [
        orm.StageItemInput(
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
        for stage_item_input in inputs
    ]
    if not entities:
        return []
    session.add_all(entities)
    await session.flush()
    return [StageItemInputBase.model_validate(entity) for entity in entities]


async def sql_update_stage_item_input(
    session: AsyncSession,
    tournament_id: TournamentId,
    stage_item_id: StageItemId,
    stage_item_input_id: StageItemInputId,
    body: StageItemInputUpdateBody,
) -> None:
    entity = await session.scalar(
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
        await session.flush()
