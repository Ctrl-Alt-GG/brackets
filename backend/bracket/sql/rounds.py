from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncConnection

from bracket.models.db.round import RoundInsertable
from bracket.models.db.util import RoundWithMatches
from bracket.sql.stage_items import get_stage_item
from bracket.sql.stages import get_full_tournament_details
from bracket.utils.id_types import RoundId, StageItemId, TournamentId


async def sql_create_round(conn: AsyncConnection, round_: RoundInsertable) -> RoundId:
    query = """
        INSERT INTO rounds (created, is_draft, name, stage_item_id)
        VALUES (NOW(), :is_draft, :name, :stage_item_id)
        RETURNING id
        """
    round_id = await conn.scalar(
        text(query),
        {
            "name": round_.name,
            "is_draft": round_.is_draft,
            "stage_item_id": round_.stage_item_id,
        },
    )
    return RoundId(round_id)


async def get_rounds_for_stage_item(
    conn: AsyncConnection, tournament_id: TournamentId, stage_item_id: StageItemId
) -> list[RoundWithMatches]:
    stage_item = await get_stage_item(conn, tournament_id, stage_item_id)
    return stage_item.rounds


async def get_round_by_id(
    conn: AsyncConnection, tournament_id: TournamentId, round_id: RoundId
) -> RoundWithMatches:
    stages = await get_full_tournament_details(
        conn, tournament_id, no_draft_rounds=False, round_id=round_id
    )

    for stage in stages:
        for stage_item in stage.stage_items:
            for round_ in stage_item.rounds:
                if round_ is not None:
                    return round_

    raise ValueError(f"Could not find round with id {round_id} for tournament {tournament_id}")


async def get_next_round_name(
    conn: AsyncConnection, tournament_id: TournamentId, stage_item_id: StageItemId
) -> str:
    query = """
        SELECT count(*) FROM rounds
        JOIN stage_items on stage_items.id = rounds.stage_item_id
        JOIN stages on stage_items.stage_id = stages.id
        WHERE stages.tournament_id = :tournament_id
        AND rounds.stage_item_id = :stage_item_id
    """
    round_count = int(
        await conn.scalar(
            text(query), {"tournament_id": tournament_id, "stage_item_id": stage_item_id}
        )
        or 0
    )
    return f"Round {round_count + 1:02d}"


async def sql_delete_rounds_for_stage_item_id(
    conn: AsyncConnection, stage_item_id: StageItemId
) -> None:
    query = """
        DELETE FROM rounds
        WHERE rounds.stage_item_id = :stage_item_id
        """
    await conn.execute(text(query), {"stage_item_id": stage_item_id})


async def sql_delete_round(conn: AsyncConnection, round_id: RoundId) -> None:
    query = """
        DELETE FROM rounds
        WHERE rounds.id = :round_id
    """
    await conn.execute(text(query), {"round_id": round_id})
