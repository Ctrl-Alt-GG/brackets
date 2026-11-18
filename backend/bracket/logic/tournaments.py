from typing import NamedTuple

from sqlalchemy.ext.asyncio import AsyncSession

from bracket.logic.planning.matches import schedule_all_matches
from bracket.logic.ranking.calculation import get_team_rankings_lookup_for_tournament
from bracket.logic.ranking.players import get_players_with_statistics
from bracket.logic.ranking.team_totals import add_team_totals, get_team_totals
from bracket.logic.scheduling.advancement import (
    get_adjacent_stage,
    get_updates_to_inputs_in_activated_stage,
)
from bracket.logic.scheduling.builder import determine_available_inputs
from bracket.logic.subscriptions import Limit, check_requirement
from bracket.logic.teams import get_teams_with_totals
from bracket.logic.tournament_graph import TournamentGraph
from bracket.models.db.ranking import RankingCreateBody
from bracket.models.db.stage_tree import StageWithStageItems
from bracket.models.db.tournament import Tournament, TournamentBody, TournamentUpdateBody
from bracket.models.db.tournament_details import (
    StageItemInputStanding,
    TournamentDetails,
    TournamentWorkspace,
)
from bracket.models.db.user import UserPublic
from bracket.sql.clubs import lock_club_for_new_tournament
from bracket.sql.rankings import get_all_rankings_in_tournament, sql_create_ranking
from bracket.sql.stages import get_full_tournament_details
from bracket.sql.tournaments import (
    count_tournaments_of_club,
    get_tournament_logo_paths,
    sql_create_tournament,
    sql_delete_tournament,
    sql_get_tournament,
    sql_update_tournament,
)
from bracket.sql.users import get_user_access_to_club
from bracket.utils.errors import UniqueIndex, check_unique_constraint_violation, forbidden
from bracket.utils.id_types import StageItemId, TournamentId
from bracket.utils.pagination import MAX_PAGE_SIZE, ParticipantPagination


class TournamentUploads(NamedTuple):
    """The files of a deleted tournament, which the caller removes once that is committed."""

    tournament_logo: str | None
    team_logos: list[str | None]


async def create_tournament(
    session: AsyncSession, body: TournamentBody, user: UserPublic
) -> Tournament:
    """
    Create a tournament in an event the user runs, with the default ranking. Who runs the event
    and how many tournaments it has are checked under the event's lock, so a concurrent change of
    either can't slip in between.
    """
    if not await lock_club_for_new_tournament(
        session, body.club_id
    ) or not await get_user_access_to_club(session, body.club_id, user.id):
        raise forbidden("Club ID is invalid")
    check_requirement(
        Limit.TOURNAMENTS, await count_tournaments_of_club(session, body.club_id), user
    )

    with check_unique_constraint_violation({UniqueIndex.ix_tournaments_dashboard_endpoint_lower}):
        tournament_id = await sql_create_tournament(session, body)

    await sql_create_ranking(session, tournament_id, RankingCreateBody(), position=0)
    return await sql_get_tournament(session, tournament_id)


async def update_tournament(
    session: AsyncSession, tournament_id: TournamentId, body: TournamentUpdateBody
) -> None:
    with check_unique_constraint_violation({UniqueIndex.ix_tournaments_dashboard_endpoint_lower}):
        await sql_update_tournament(session, tournament_id, body)

    await schedule_all_matches(session, tournament_id)


async def delete_tournament_completely(
    session: AsyncSession, tournament_id: TournamentId
) -> TournamentUploads:
    """
    Delete the tournament and everything in it.

    Returns its logos, which the caller discards once the deletion is committed.
    """
    tournament_logo, team_logos = await get_tournament_logo_paths(session, tournament_id)
    await sql_delete_tournament(session, tournament_id)
    return TournamentUploads(tournament_logo=tournament_logo, team_logos=team_logos)


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


async def get_tournament_workspace(
    session: AsyncSession, tournament_id: TournamentId
) -> TournamentWorkspace:
    """Everything the organizers' pages of a tournament show, from one snapshot."""
    graph = TournamentGraph(await get_full_tournament_details(session, tournament_id))
    totals = await get_team_totals(session, tournament_id)
    await add_team_totals(session, tournament_id, graph, totals=totals)
    teams = await get_teams_with_totals(
        session,
        tournament_id,
        pagination=ParticipantPagination(limit=MAX_PAGE_SIZE),
        totals=totals,
    )
    next_stage = get_adjacent_stage(graph.stages, "next")
    # Standings and players' results only count published rounds, so the drafts can stay in.
    return TournamentWorkspace(
        tournament=await sql_get_tournament(session, tournament_id),
        stages=graph.stages,
        players=await get_players_with_statistics(
            session, tournament_id, stages=graph.stages, teams=teams
        ),
        teams=teams,
        rankings=await get_all_rankings_in_tournament(session, tournament_id),
        standings=await get_tournament_standings(session, tournament_id, graph.stages),
        available_inputs=determine_available_inputs(teams, graph.stages),
        next_stage_rankings=(
            await get_updates_to_inputs_in_activated_stage(
                session, tournament_id, graph.stages, next_stage.id
            )
            if next_stage is not None
            else {}
        ),
    )


async def get_tournament_details(
    session: AsyncSession, tournament_id: TournamentId
) -> TournamentDetails:
    """Everything the Details pages of a tournament show, as visitors may see it."""
    graph = TournamentGraph(
        await get_full_tournament_details(session, tournament_id, no_draft_rounds=True)
    )
    totals = await get_team_totals(session, tournament_id)
    await add_team_totals(session, tournament_id, graph, totals=totals)
    teams = await get_teams_with_totals(session, tournament_id, totals=totals)
    return TournamentDetails(
        tournament=await sql_get_tournament(session, tournament_id),
        stages=graph.stages,
        players=await get_players_with_statistics(
            session, tournament_id, stages=graph.stages, teams=teams
        ),
        teams=teams,
        rankings=await get_all_rankings_in_tournament(session, tournament_id),
        standings=await get_tournament_standings(session, tournament_id, graph.stages),
    )
