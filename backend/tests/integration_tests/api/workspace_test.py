from http import HTTPMethod
from typing import Any

import pytest
from sqlalchemy import update

from bracket import orm
from bracket.database import session_scope
from bracket.logic import tournaments as tournament_logic
from bracket.logic.ranking import team_totals
from bracket.utils.id_types import StageItemId, TournamentId
from tests.integration_tests.api.flows import api_tournament
from tests.integration_tests.api.shared import send_request
from tests.integration_tests.models import AuthContext


@pytest.mark.asyncio(loop_scope="session")
async def test_the_workspace_is_for_organizers(
    startup_and_shutdown_uvicorn_server: None, auth_context: AuthContext
) -> None:
    async with api_tournament(auth_context) as flow:
        teams = await flow.add_teams("Alpha", "Bravo")
        group = await flow.add_stage_item(await flow.add_stage(), "ROUND_ROBIN", 2, "Group")
        await flow.fill(group, *teams.values())

        workspace = (await flow.call(HTTPMethod.GET, "workspace"))["data"]
        assert [team["name"] for team in workspace["teams"]] == ["Alpha", "Bravo"]
        assert [item["name"] for item in workspace["stages"][0]["stage_items"]] == ["Group"]
        assert set(workspace) >= {"available_inputs", "next_stage_rankings", "standings"}

        visitor = await send_request(HTTPMethod.GET, f"tournaments/{flow.id}/workspace")
        assert visitor == {"detail": "Could not validate credentials"}


@pytest.mark.asyncio(loop_scope="session")
async def test_a_result_saved_meanwhile_shows_in_none_of_the_workspace(
    startup_and_shutdown_uvicorn_server: None,
    auth_context: AuthContext,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async with api_tournament(auth_context) as flow:
        teams = await flow.add_teams("Alpha", "Bravo")
        group = await flow.add_stage_item(await flow.add_stage(), "ROUND_ROBIN", 2, "Group")
        await flow.fill(group, *teams.values())
        await flow.activate()
        [[match]] = await flow.matches(group)

        totals = team_totals.get_team_totals

        async def save_a_result_first(*args: Any) -> Any:
            # After the stages were read, and before the results of the teams are.
            async with session_scope() as other:
                await other.execute(
                    update(orm.Match)
                    .where(orm.Match.id == match["id"])
                    .values(stage_item_input1_score=3, stage_item_input2_score=1)
                )
            return await totals(*args)

        monkeypatch.setattr(tournament_logic, "get_team_totals", save_a_result_first)
        async with session_scope(read_only=True) as session:
            workspace = await tournament_logic.get_tournament_workspace(
                session, TournamentId(flow.id)
            )

        [loaded] = workspace.stages[0].stage_items[0].rounds[0].matches
        assert not loaded.played
        assert all(team.wins == 0 and team.losses == 0 for team in workspace.teams)
        assert all(standing.wins == 0 for standing in workspace.standings[StageItemId(group)])
