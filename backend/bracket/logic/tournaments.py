from typing import NamedTuple

from sqlalchemy.ext.asyncio import AsyncConnection

from bracket.logic.ranking.calculation import get_team_rankings_lookup_for_tournament
from bracket.logic.ranking.players import get_players_with_statistics
from bracket.models.db.tournament_details import StageItemInputStanding, TournamentDetails
from bracket.sql.players import sql_delete_players_of_tournament
from bracket.sql.rankings import get_all_rankings_in_tournament, sql_delete_ranking
from bracket.sql.shared import sql_delete_stage_item_matches, sql_delete_stage_item_relations
from bracket.sql.stage_items import sql_delete_stage_item
from bracket.sql.stages import get_full_tournament_details, sql_delete_stage
from bracket.sql.teams import get_teams_with_members, sql_delete_teams_of_tournament
from bracket.sql.tournaments import sql_delete_tournament, sql_get_tournament
from bracket.utils.id_types import StageItemId, TournamentId
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


class TournamentUploads(NamedTuple):
    """The files of a deleted tournament, which the caller removes once that is committed."""

    tournament_logo: str | None
    team_logos: list[str | None]


async def sql_delete_tournament_completely(
    conn: AsyncConnection, tournament_id: TournamentId
) -> TournamentUploads:
    """
    Delete the tournament and everything in it.

    Returns its logos, which the caller discards once the deletion is committed.
    """
    tournament = await sql_get_tournament(conn, tournament_id)
    stages = await get_full_tournament_details(conn, tournament_id)
    team_logos: list[str | None] = [
        team.logo_path for team in await get_teams_with_members(conn, tournament_id)
    ]

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
    return TournamentUploads(tournament_logo=tournament.logo_path, team_logos=team_logos)


async def get_tournament_standings(
    conn: AsyncConnection, tournament_id: TournamentId
) -> dict[StageItemId, list[StageItemInputStanding]]:
    """The teams of every stage item, best first. Teams advance to the next stage in this order."""
    stages = await get_full_tournament_details(conn, tournament_id, no_draft_rounds=True)
    team_rankings = await get_team_rankings_lookup_for_tournament(conn, tournament_id, stages)
    return {
        stage_item_id: [
            StageItemInputStanding(stage_item_input_id=input_id, **statistics.model_dump())
            for input_id, statistics in team_ranking
        ]
        for stage_item_id, team_ranking in team_rankings.items()
    }


async def get_tournament_details(
    conn: AsyncConnection, tournament_id: TournamentId
) -> TournamentDetails:
    """Everything the Details pages of a tournament show, as visitors may see it."""
    stages = await get_full_tournament_details(conn, tournament_id, no_draft_rounds=True)
    teams = await get_teams_with_members(conn, tournament_id)
    return TournamentDetails(
        tournament=await sql_get_tournament(conn, tournament_id),
        stages=stages,
        players=await get_players_with_statistics(conn, tournament_id, stages=stages, teams=teams),
        teams=teams,
        rankings=await get_all_rankings_in_tournament(conn, tournament_id),
        standings=await get_tournament_standings(conn, tournament_id),
    )
