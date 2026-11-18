"""
A command that changes the loaded tournament graph leaves it as the database has it, so the same
graph can be used for rankings, scheduling and conflicts afterwards.
"""

from typing import Any

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from bracket.database import session_factory
from bracket.logic.ranking.elimination import update_inputs_in_subsequent_elimination_rounds
from bracket.logic.stages import advance_teams_into_stage, release_teams_from_stage
from bracket.logic.tournament_graph import TournamentGraph
from bracket.models.db.match import MatchBody
from bracket.sql.matches import sql_update_match
from bracket.sql.stages import get_full_tournament_details
from bracket.utils.id_types import StageId, StageItemId, TournamentId
from tests.integration_tests.api.flows import api_tournament
from tests.integration_tests.models import AuthContext

# Statistics stored with a slot are refreshed in the database only; standings replay the matches.
SLOT_STATISTICS = {"points", "wins", "draws", "losses"}


def comparable(value: Any) -> Any:
    if isinstance(value, dict):
        left_out = SLOT_STATISTICS if "slot" in value else set()
        return {key: comparable(item) for key, item in value.items() if key not in left_out}
    if isinstance(value, list):
        return [comparable(item) for item in value]
    return value


async def assert_graph_is_stored(
    session: AsyncSession, tournament_id: TournamentId, graph: TournamentGraph
) -> None:
    stored = await get_full_tournament_details(session, tournament_id)
    assert comparable([stage.model_dump(mode="json") for stage in graph.stages]) == comparable(
        [stage.model_dump(mode="json") for stage in stored]
    )


async def record(
    session: AsyncSession,
    graph: TournamentGraph,
    stage_item_id: StageItemId,
    score: tuple[int, int],
) -> None:
    """A result of the first knockout match, as recording one changes the graph."""
    stage_item = graph.stage_item(stage_item_id)
    first_round = min(stage_item.rounds, key=lambda round_: round_.id)
    match = first_round.matches[0]
    body = MatchBody(stage_item_input1_score=score[0], stage_item_input2_score=score[1])
    await sql_update_match(session, match.id, body)
    graph.update_match(match.id, **body.model_dump())
    await update_inputs_in_subsequent_elimination_rounds(
        session, graph, stage_item, first_round.id, {match.id}
    )


@pytest.mark.asyncio(loop_scope="session")
async def test_activation_results_and_going_back_keep_the_graph_stored(
    startup_and_shutdown_uvicorn_server: None, auth_context: AuthContext
) -> None:
    async with api_tournament(auth_context) as flow:
        teams = await flow.add_teams("Alpha", "Bravo", "Charlie", "Delta")
        groups = await flow.add_stage()
        group = await flow.add_stage_item(groups, "ROUND_ROBIN", 4, "Group")
        playoffs = await flow.add_stage()
        knockout = await flow.add_stage_item(playoffs, "SINGLE_ELIMINATION", 4, "Playoffs")
        await flow.fill(group, *teams.values())
        await flow.feed(knockout, group, 1, 4, 2, 3)
        await flow.activate()
        for matches in await flow.matches(group):
            for index, match in enumerate(matches):
                await flow.score(match, 3, index)

        tournament_id = TournamentId(flow.id)
        async with session_factory() as session:
            try:
                graph = TournamentGraph(await get_full_tournament_details(session, tournament_id))
                await advance_teams_into_stage(session, tournament_id, graph, StageId(playoffs))
                await assert_graph_is_stored(session, tournament_id, graph)

                await record(session, graph, StageItemId(knockout), (2, 1))
                await assert_graph_is_stored(session, tournament_id, graph)
                # A correction changes who reached the final, and clears the final's result.
                await record(session, graph, StageItemId(knockout), (1, 2))
                await assert_graph_is_stored(session, tournament_id, graph)

                stage = next(stage for stage in graph.stages if stage.id == playoffs)
                await release_teams_from_stage(session, tournament_id, graph, stage)
                await assert_graph_is_stored(session, tournament_id, graph)
            finally:
                await session.rollback()
