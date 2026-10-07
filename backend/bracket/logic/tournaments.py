from sqlalchemy.ext.asyncio import AsyncConnection

from bracket.sql.players import sql_delete_players_of_tournament
from bracket.sql.rankings import get_all_rankings_in_tournament, sql_delete_ranking
from bracket.sql.shared import sql_delete_stage_item_matches, sql_delete_stage_item_relations
from bracket.sql.stage_items import sql_delete_stage_item
from bracket.sql.stages import get_full_tournament_details, sql_delete_stage
from bracket.sql.teams import sql_delete_teams_of_tournament
from bracket.sql.tournaments import sql_delete_tournament, sql_get_tournament
from bracket.utils.id_types import TournamentId
from bracket.utils.uploads import get_existing_upload_path, remove_existing_upload


async def get_tournament_logo_path(
    conn: AsyncConnection, tournament_id: TournamentId
) -> str | None:
    tournament = await sql_get_tournament(conn, tournament_id)
    logo_path = await get_existing_upload_path("tournament-logos", tournament.logo_path)
    return str(logo_path) if logo_path is not None else None


async def delete_tournament_logo(conn: AsyncConnection, tournament_id: TournamentId) -> None:
    tournament = await sql_get_tournament(conn, tournament_id)
    await remove_existing_upload("tournament-logos", tournament.logo_path)


async def sql_delete_tournament_completely(
    conn: AsyncConnection, tournament_id: TournamentId
) -> str | None:
    """
    Delete the tournament and everything in it.

    Returns the tournament's logo, which the caller discards once the deletion is committed.
    """
    tournament = await sql_get_tournament(conn, tournament_id)
    stages = await get_full_tournament_details(conn, tournament_id)

    for stage in stages:
        for stage_item in stage.stage_items:
            await sql_delete_stage_item_matches(conn, stage_item.id)

    for stage in stages:
        for stage_item in stage.stage_items:
            await sql_delete_stage_item_relations(conn, stage_item.id)

    for stage in stages:
        for stage_item in stage.stage_items:
            await sql_delete_stage_item(conn, stage_item.id)

        await sql_delete_stage(conn, tournament_id, stage.id)

    for ranking in await get_all_rankings_in_tournament(conn, tournament_id):
        await sql_delete_ranking(conn, tournament_id, ranking.id)

    await sql_delete_players_of_tournament(conn, tournament_id)
    await sql_delete_teams_of_tournament(conn, tournament_id)
    await sql_delete_tournament(conn, tournament_id)
    return tournament.logo_path
