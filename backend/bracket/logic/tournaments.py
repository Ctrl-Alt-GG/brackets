from typing import NamedTuple

from sqlalchemy.ext.asyncio import AsyncSession

from bracket.logic.ranking.calculation import get_team_rankings_lookup_for_tournament
from bracket.logic.ranking.players import get_players_with_statistics
from bracket.logic.ranking.team_totals import get_team_totals
from bracket.models.db.tournament_details import StageItemInputStanding, TournamentDetails
from bracket.models.db.util import StageWithStageItems
from bracket.sql.rankings import get_all_rankings_in_tournament
from bracket.sql.stages import add_team_totals, get_full_tournament_details
from bracket.sql.teams import get_team_logo_paths, get_teams_with_members
from bracket.sql.tournaments import sql_delete_tournament, sql_get_tournament
from bracket.utils.id_types import StageItemId, TournamentId
from bracket.utils.uploads import get_existing_upload_path


async def get_tournament_logo_path(
    session: AsyncSession, tournament_id: TournamentId
) -> str | None:
    tournament = await sql_get_tournament(session, tournament_id)
    logo_path = await get_existing_upload_path("tournament-logos", tournament.logo_path)
    return str(logo_path) if logo_path is not None else None


class TournamentUploads(NamedTuple):
    """The files of a deleted tournament, which the caller removes once that is committed."""

    tournament_logo: str | None
    team_logos: list[str | None]


async def sql_delete_tournament_completely(
    session: AsyncSession, tournament_id: TournamentId
) -> TournamentUploads:
    """
    Delete the tournament and everything in it.

    Returns its logos, which the caller discards once the deletion is committed.
    """
    tournament = await sql_get_tournament(session, tournament_id)
    team_logos = await get_team_logo_paths(session, tournament_id)
    await sql_delete_tournament(session, tournament_id)
    return TournamentUploads(tournament_logo=tournament.logo_path, team_logos=team_logos)


async def get_tournament_standings(
    session: AsyncSession,
    tournament_id: TournamentId,
    stages: list[StageWithStageItems] | None = None,
) -> dict[StageItemId, list[StageItemInputStanding]]:
    """
    The teams of every stage item, best first. Teams advance to the next stage in this order.

    `stages` (without draft rounds) can be passed by a caller that has them.
    """
    if stages is None:
        stages = await get_full_tournament_details(session, tournament_id, no_draft_rounds=True)
    team_rankings = await get_team_rankings_lookup_for_tournament(session, tournament_id, stages)
    return {
        stage_item_id: [
            StageItemInputStanding(
                stage_item_input_id=placing.stage_item_input_id,
                **placing.statistics.model_dump(),
            )
            for placing in team_ranking
        ]
        for stage_item_id, team_ranking in team_rankings.items()
    }


async def get_tournament_details(
    session: AsyncSession, tournament_id: TournamentId
) -> TournamentDetails:
    """Everything the Details pages of a tournament show, as visitors may see it."""
    stages = await get_full_tournament_details(session, tournament_id, no_draft_rounds=True)
    totals = await get_team_totals(session, tournament_id)
    await add_team_totals(session, tournament_id, stages, totals=totals)
    teams = await get_teams_with_members(session, tournament_id, totals=totals)
    return TournamentDetails(
        tournament=await sql_get_tournament(session, tournament_id),
        stages=stages,
        players=await get_players_with_statistics(
            session, tournament_id, stages=stages, teams=teams
        ),
        teams=teams,
        rankings=await get_all_rankings_in_tournament(session, tournament_id),
        standings=await get_tournament_standings(session, tournament_id, stages),
    )
