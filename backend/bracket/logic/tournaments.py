from fastapi import HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from starlette import status

from bracket.logic.participation import follow_rosters, get_tournament_teams_with_totals
from bracket.logic.planning.conflicts import get_schedule_conflicts
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
from bracket.logic.tournament_graph import TournamentGraph
from bracket.models.db.ranking import RankingCreateBody
from bracket.models.db.stage_tree import StageWithStageItems
from bracket.models.db.tournament import Tournament, TournamentBody
from bracket.models.db.tournament_details import (
    StageItemInputStanding,
    TournamentDetails,
    TournamentWorkspace,
)
from bracket.models.db.user import UserPublic
from bracket.models.enums import TournamentRole, TournamentStatus
from bracket.sql.organizers import count_owned_tournaments, sql_add_organizer
from bracket.sql.participation import LineupScope, get_participating_team_ids
from bracket.sql.rankings import get_all_rankings_in_tournament, sql_create_ranking
from bracket.sql.stages import get_full_tournament_details
from bracket.sql.teams import lock_teams_against_changes
from bracket.sql.tournaments import (
    sql_create_tournament,
    sql_delete_tournament,
    sql_get_tournament,
    sql_update_tournament,
    sql_update_tournament_status,
)
from bracket.sql.users import lock_user
from bracket.utils.errors import UniqueIndex, check_unique_constraint_violation
from bracket.utils.i18n import gettext
from bracket.utils.id_types import StageItemId, TournamentId
from bracket.utils.pagination import MAX_PAGE_SIZE, TeamPagination


async def create_tournament(
    session: AsyncSession, body: TournamentBody, user: UserPublic
) -> Tournament:
    """
    Create a tournament that the user owns, with the default ranking. How many tournaments the
    account owns is counted under the account's lock, so that two creations can't both take the
    last place the limit allows.
    """
    await lock_user(session, user.id)
    check_requirement(Limit.TOURNAMENTS, await count_owned_tournaments(session, user.id), user)

    with check_unique_constraint_violation({UniqueIndex.ix_tournaments_dashboard_endpoint_lower}):
        tournament_id = await sql_create_tournament(session, body)

    await sql_add_organizer(session, tournament_id, user.id, TournamentRole.OWNER)
    await sql_create_ranking(session, tournament_id, RankingCreateBody(), position=0)
    return await sql_get_tournament(session, tournament_id)


async def update_tournament(
    session: AsyncSession, tournament_id: TournamentId, body: TournamentBody
) -> None:
    with check_unique_constraint_violation({UniqueIndex.ix_tournaments_dashboard_endpoint_lower}):
        await sql_update_tournament(session, tournament_id, body)

    await schedule_all_matches(session, tournament_id)


async def change_tournament_status(
    session: AsyncSession, tournament: Tournament, new_status: TournamentStatus
) -> None:
    """
    Archive the tournament, which keeps its lineups as they are, or reopen it. A reopened
    tournament's lineups follow its teams' rosters again, which may have changed meanwhile, and its
    schedule makes room for what its players play elsewhere.
    """
    if tournament.status is new_status:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=gettext("Tournament already has the requested status"),
        )

    await sql_update_tournament_status(session, tournament.id, new_status)
    if new_status is TournamentStatus.OPEN:
        await lock_teams_against_changes(
            session, await get_participating_team_ids(session, tournament.id)
        )
        await follow_rosters(session, LineupScope.of_tournament(tournament.id))
        await schedule_all_matches(session, tournament.id)


async def delete_tournament(session: AsyncSession, tournament_id: TournamentId) -> str | None:
    """
    Delete the tournament and everything in it. Its teams and players stay.

    Returns its logo, which the caller discards once the deletion is committed.
    """
    logo_path = (await sql_get_tournament(session, tournament_id)).logo_path
    await sql_delete_tournament(session, tournament_id)
    return logo_path


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
    tournament = await sql_get_tournament(session, tournament_id)
    graph = TournamentGraph(await get_full_tournament_details(session, tournament_id))
    totals = await get_team_totals(session, tournament_id)
    await add_team_totals(session, tournament_id, graph, totals=totals)
    teams = await get_tournament_teams_with_totals(
        session, tournament_id, pagination=TeamPagination(limit=MAX_PAGE_SIZE), totals=totals
    )
    next_stage = get_adjacent_stage(graph.stages, "next")
    # Standings and players' results only count published rounds, so the drafts can stay in.
    return TournamentWorkspace(
        tournament=tournament,
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
        conflicts=await get_schedule_conflicts(session, tournament, graph.stages),
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
    teams = await get_tournament_teams_with_totals(session, tournament_id, totals=totals)
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
