import re
from collections.abc import Sequence

from fastapi import HTTPException
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession
from starlette import status

from bracket import orm
from bracket.models.db.round import Round, RoundUpdateBody
from bracket.models.db.stage_tree import RoundWithMatches
from bracket.sql.stages import get_full_tournament_details
from bracket.utils.id_types import RoundId, StageItemId, TournamentId


async def sql_create_rounds(
    session: AsyncSession,
    tournament_id: TournamentId,
    stage_item_id: StageItemId,
    names: Sequence[str],
    *,
    is_draft: bool,
) -> list[RoundId]:
    """Add rounds with these names to the stage item, in this order."""
    entities = [
        orm.Round(
            tournament_id=tournament_id, stage_item_id=stage_item_id, name=name, is_draft=is_draft
        )
        for name in names
    ]
    if not entities:
        return []
    session.add_all(entities)
    await session.flush()
    return [RoundId(entity.id) for entity in entities]


async def get_round(
    session: AsyncSession, tournament_id: TournamentId, round_id: RoundId
) -> Round | None:
    entity = await session.scalar(
        select(orm.Round)
        .where(orm.Round.id == round_id, orm.Round.tournament_id == tournament_id)
        .execution_options(populate_existing=True)
    )
    return Round.model_validate(entity) if entity is not None else None


async def get_round_by_id(
    session: AsyncSession, tournament_id: TournamentId, round_id: RoundId
) -> RoundWithMatches:
    stages = await get_full_tournament_details(
        session, tournament_id, no_draft_rounds=False, round_id=round_id
    )
    for stage in stages:
        for stage_item in stage.stage_items:
            for round_ in stage_item.rounds:
                return round_
    raise HTTPException(
        status_code=status.HTTP_404_NOT_FOUND,
        detail=f"Could not find round with id {round_id}",
    )


async def get_next_round_name(
    session: AsyncSession, tournament_id: TournamentId, stage_item_id: StageItemId
) -> str:
    """Number after the highest existing round, including gaps left by deleted rounds."""
    names = list(
        await session.scalars(
            select(orm.Round.name).where(
                orm.Round.tournament_id == tournament_id, orm.Round.stage_item_id == stage_item_id
            )
        )
    )
    numbers = [int(number.group(1)) for name in names if (number := re.search(r"(\d+)\s*$", name))]
    return f"Round {max([len(names), *numbers]) + 1:02d}"


async def sql_delete_round(session: AsyncSession, round_id: RoundId) -> None:
    await session.execute(delete(orm.Round).where(orm.Round.id == round_id))


async def sql_update_round(
    session: AsyncSession, tournament_id: TournamentId, round_id: RoundId, body: RoundUpdateBody
) -> None:
    entity = await session.scalar(
        select(orm.Round)
        .where(orm.Round.tournament_id == tournament_id, orm.Round.id == round_id)
        .execution_options(populate_existing=True)
    )
    if entity is not None:
        entity.name = body.name
        entity.is_draft = body.is_draft
        await session.flush()
