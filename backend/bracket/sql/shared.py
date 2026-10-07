from sqlalchemy.ext.asyncio import AsyncConnection

from bracket.sql.stage_items import sql_delete_stage_item
from bracket.utils.id_types import StageItemId


async def sql_delete_stage_item_matches(conn: AsyncConnection, stage_item_id: StageItemId) -> None:
    from bracket.sql.matches import sql_delete_matches_for_stage_item_id

    await sql_delete_matches_for_stage_item_id(conn, stage_item_id)


async def sql_delete_stage_item_relations(
    conn: AsyncConnection, stage_item_id: StageItemId
) -> None:
    from bracket.sql.rounds import sql_delete_rounds_for_stage_item_id
    from bracket.sql.stage_item_inputs import sql_delete_stage_item_inputs

    await sql_delete_rounds_for_stage_item_id(conn, stage_item_id)
    await sql_delete_stage_item_inputs(conn, stage_item_id)


async def sql_delete_stage_item_with_foreign_keys(
    conn: AsyncConnection, stage_item_id: StageItemId
) -> None:
    from bracket.sql.matches import sql_delete_matches_for_stage_item_id
    from bracket.sql.rounds import sql_delete_rounds_for_stage_item_id
    from bracket.sql.stage_item_inputs import sql_delete_stage_item_inputs

    await sql_delete_matches_for_stage_item_id(conn, stage_item_id)
    await sql_delete_stage_item_inputs(conn, stage_item_id)
    await sql_delete_rounds_for_stage_item_id(conn, stage_item_id)
    await sql_delete_stage_item(conn, stage_item_id)
