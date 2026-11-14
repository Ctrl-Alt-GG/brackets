import re

from fastapi import HTTPException
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession
from starlette import status

from bracket import orm
from bracket.models.db.round import RoundInsertable, RoundUpdateBody
from bracket.models.db.util import RoundWithMatches
from bracket.sql.stage_items import get_stage_item
from bracket.sql.stages import get_full_tournament_details
from bracket.utils.id_types import RoundId, StageItemId, TournamentId


async def sql_create_round(conn: AsyncSession, round_: RoundInsertable) -> RoundId:
    entity = orm.Round(
        name=round_.name, is_draft=round_.is_draft, stage_item_id=round_.stage_item_id
    )
    conn.add(entity)
    await conn.flush()
    return RoundId(entity.id)


async def get_rounds_for_stage_item(
    conn: AsyncSession, tournament_id: TournamentId, stage_item_id: StageItemId
) -> list[RoundWithMatches]:
    stage_item = await get_stage_item(conn, tournament_id, stage_item_id)
    return stage_item.rounds


async def get_round_by_id(
    conn: AsyncSession, tournament_id: TournamentId, round_id: RoundId
) -> RoundWithMatches:
    stages = await get_full_tournament_details(
        conn, tournament_id, no_draft_rounds=False, round_id=round_id
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
    conn: AsyncSession, tournament_id: TournamentId, stage_item_id: StageItemId
) -> str:
    """Number after the highest existing round, including gaps left by deleted rounds."""
    names = list(
        await conn.scalars(
            select(orm.Round.name)
            .join(orm.StageItem, orm.StageItem.id == orm.Round.stage_item_id)
            .join(orm.Stage, orm.Stage.id == orm.StageItem.stage_id)
            .where(
                orm.Stage.tournament_id == tournament_id, orm.Round.stage_item_id == stage_item_id
            )
        )
    )
    numbers = [int(number.group(1)) for name in names if (number := re.search(r"(\d+)\s*$", name))]
    return f"Round {max([len(names), *numbers]) + 1:02d}"


async def sql_delete_rounds_for_stage_item_id(
    conn: AsyncSession, stage_item_id: StageItemId
) -> None:
    await conn.execute(delete(orm.Round).where(orm.Round.stage_item_id == stage_item_id))


async def sql_delete_round(conn: AsyncSession, round_id: RoundId) -> None:
    await conn.execute(delete(orm.Round).where(orm.Round.id == round_id))


async def sql_update_round(
    conn: AsyncSession, tournament_id: TournamentId, round_id: RoundId, body: RoundUpdateBody
) -> None:
    entity = await conn.scalar(
        select(orm.Round)
        .join(orm.StageItem, orm.StageItem.id == orm.Round.stage_item_id)
        .join(orm.Stage, orm.Stage.id == orm.StageItem.stage_id)
        .where(orm.Stage.tournament_id == tournament_id, orm.Round.id == round_id)
        .execution_options(populate_existing=True)
    )
    if entity is not None:
        entity.name = body.name
        entity.is_draft = body.is_draft
        await conn.flush()
