from decimal import Decimal
from http import HTTPMethod

import pytest
from sqlalchemy import event
from sqlalchemy.ext.asyncio import AsyncConnection

from bracket.models.db.stage_item_inputs import StageItemInputFinal
from bracket.sql.stages import get_full_tournament_details
from bracket.sql.teams import get_team_by_id
from bracket.utils.id_types import RoundId, StageId, StageItemId, TeamId, TournamentId
from bracket.utils.types import JsonDict
from tests.integration_tests.api.flows import TournamentFlow, api_tournament
from tests.integration_tests.api.shared import SUCCESS_RESPONSE
from tests.integration_tests.models import AuthContext


async def team_totals(flow: TournamentFlow) -> dict[str, JsonDict]:
    response = await flow.call(HTTPMethod.GET, "teams?limit=500")
    return {team["name"]: team for team in response["data"]["teams"]}


def assert_totals(
    team: JsonDict, *, wins: int = 0, draws: int = 0, losses: int = 0, elo: int = 1200
) -> None:
    assert (team["wins"], team["draws"], team["losses"]) == (wins, draws, losses)
    assert Decimal(team["elo_score"]) == elo
    assert Decimal(team["swiss_score"]) == Decimal(wins) + Decimal(draws) / 2


@pytest.mark.asyncio(loop_scope="session")
async def test_team_totals_follow_played_corrected_cleared_and_deleted_results(
    startup_and_shutdown_uvicorn_server: None, auth_context: AuthContext
) -> None:
    async with api_tournament(auth_context) as flow:
        teams = await flow.add_teams("Alpha", "Bravo")
        group = await flow.add_stage_item(await flow.add_stage(), "ROUND_ROBIN", 2, "Group")
        await flow.fill(group, *teams.values())
        await flow.activate()
        match = (await flow.matches(group))[0][0]
        for team in (await team_totals(flow)).values():
            assert_totals(team)

        assert await flow.score(match, 2, 0) == SUCCESS_RESPONSE
        played = await team_totals(flow)
        assert_totals(played["Alpha"], wins=1, elo=1216)
        assert_totals(played["Bravo"], losses=1, elo=1184)

        assert await flow.score(match, 0, 2) == SUCCESS_RESPONSE
        corrected = await team_totals(flow)
        assert_totals(corrected["Alpha"], losses=1, elo=1184)
        assert_totals(corrected["Bravo"], wins=1, elo=1216)

        assert await flow.score(match, 0, 0) == SUCCESS_RESPONSE
        for team in (await team_totals(flow)).values():
            assert_totals(team)

        assert await flow.score(match, 0, 0, scoreless_result=True) == SUCCESS_RESPONSE
        for team in (await team_totals(flow)).values():
            assert_totals(team, draws=1)

        assert await flow.call(HTTPMethod.DELETE, f"stage_items/{group}") == SUCCESS_RESPONSE
        for team in (await team_totals(flow)).values():
            assert_totals(team)


@pytest.mark.asyncio(loop_scope="session")
async def test_draft_results_count_only_while_published(
    startup_and_shutdown_uvicorn_server: None, auth_context: AuthContext
) -> None:
    async with api_tournament(auth_context) as flow:
        teams = await flow.add_teams("Alpha", "Bravo")
        swiss = await flow.add_stage_item(await flow.add_stage(), "SWISS", 2, "Swiss")
        await flow.fill(swiss, *teams.values())
        await flow.activate()
        assert (
            await flow.call(HTTPMethod.POST, "rounds", {"stage_item_id": swiss}) == SUCCESS_RESPONSE
        )
        round_ = (await flow.stage_item(swiss))["rounds"][0]
        match = round_["matches"][0]
        assert await flow.score(match, 3, 1) == SUCCESS_RESPONSE
        for team in (await team_totals(flow)).values():
            assert_totals(team)

        assert (
            await flow.call(
                HTTPMethod.PUT,
                f"rounds/{round_['id']}",
                {"name": round_["name"], "is_draft": False},
            )
            == SUCCESS_RESPONSE
        )
        published = await team_totals(flow)
        winner = match["stage_item_input1"]["team"]["name"]
        loser = match["stage_item_input2"]["team"]["name"]
        assert_totals(published[winner], wins=1, elo=1216)
        assert_totals(published[loser], losses=1, elo=1184)

        assert (
            await flow.call(
                HTTPMethod.PUT, f"rounds/{round_['id']}", {"name": round_["name"], "is_draft": True}
            )
            == SUCCESS_RESPONSE
        )
        for team in (await team_totals(flow)).values():
            assert_totals(team)
        assert await flow.call(HTTPMethod.DELETE, f"matches/{match['id']}") == SUCCESS_RESPONSE
        for team in (await team_totals(flow)).values():
            assert_totals(team)


@pytest.mark.asyncio(loop_scope="session")
async def test_statistic_sorting_happens_before_pagination(
    startup_and_shutdown_uvicorn_server: None, auth_context: AuthContext
) -> None:
    async with api_tournament(auth_context) as flow:
        teams = await flow.add_teams("Alpha", "Bravo", "Zulu")
        group = await flow.add_stage_item(await flow.add_stage(), "ROUND_ROBIN", 2, "Group")
        await flow.fill(group, teams["Zulu"], teams["Alpha"])
        await flow.activate()
        assert await flow.score((await flow.matches(group))[0][0], 2, 0) == SUCCESS_RESPONSE

        for sort_by in ("wins", "elo_score", "swiss_score"):
            first = await flow.call(
                HTTPMethod.GET, f"teams?sort_by={sort_by}&sort_direction=desc&limit=1&offset=0"
            )
            assert first["data"]["count"] == 3
            assert [team["name"] for team in first["data"]["teams"]] == ["Zulu"]
        second = await flow.call(
            HTTPMethod.GET, "teams?sort_by=elo_score&sort_direction=desc&limit=1&offset=1"
        )
        assert [team["name"] for team in second["data"]["teams"]] == ["Bravo"]
        losers = await flow.call(
            HTTPMethod.GET, "teams?sort_by=losses&sort_direction=desc&limit=1&offset=0"
        )
        assert [team["name"] for team in losers["data"]["teams"]] == ["Alpha"]
        assert (
            await flow.score((await flow.matches(group))[0][0], 0, 0, scoreless_result=True)
            == SUCCESS_RESPONSE
        )
        draws = await flow.call(
            HTTPMethod.GET, "teams?sort_by=draws&sort_direction=desc&limit=1&offset=1"
        )
        assert [team["name"] for team in draws["data"]["teams"]] == ["Zulu"]


@pytest.mark.asyncio(loop_scope="session")
async def test_filtered_stage_responses_keep_tournament_totals_without_duplicate_items(
    conn: AsyncConnection, startup_and_shutdown_uvicorn_server: None, auth_context: AuthContext
) -> None:
    async with api_tournament(auth_context) as flow:
        teams = await flow.add_teams("Alpha", "Bravo")
        stage = await flow.add_stage()
        group_a = await flow.add_stage_item(stage, "ROUND_ROBIN", 2, "Group A")
        group_b = await flow.add_stage_item(stage, "ROUND_ROBIN", 2, "Group B")
        await flow.fill(group_a, *teams.values())
        await flow.fill(group_b, *teams.values())
        await flow.activate()
        for group in (group_a, group_b):
            assert await flow.score((await flow.matches(group))[0][0], 2, 0) == SUCCESS_RESPONSE
        group_c = await flow.add_stage_item(await flow.add_stage(), "ROUND_ROBIN", 2, "Group C")
        await flow.fill(group_c, *teams.values())
        await flow.activate()
        assert await flow.score((await flow.matches(group_c))[0][0], 2, 0) == SUCCESS_RESPONSE
        ordinary = await team_totals(flow)
        assert_totals(ordinary["Alpha"], wins=3, elo=1244)
        assert_totals(ordinary["Bravo"], losses=3, elo=1156)
        single = await get_team_by_id(conn, TeamId(teams["Alpha"]), TournamentId(flow.id))
        assert single is not None
        assert_totals(single.model_dump(mode="json"), wins=3, elo=1244)

        query_count = 0

        def count_queries(_conn: object, _cursor: object, statement: str, *_args: object) -> None:
            nonlocal query_count
            if statement.lstrip().lower().startswith(("select", "with")):
                query_count += 1

        event.listen(conn.sync_connection, "before_cursor_execute", count_queries)
        try:
            both = await get_full_tournament_details(
                conn,
                TournamentId(flow.id),
                stage_item_ids={StageItemId(group_a), StageItemId(group_b)},
            )
        finally:
            event.remove(conn.sync_connection, "before_cursor_execute", count_queries)
        assert query_count <= 2
        assert len(both) == 1
        assert [item.id for item in both[0].stage_items] == [group_a, group_b]
        round_id = (await flow.stage_item(group_a))["rounds"][0]["id"]
        filtered_results = [
            both,
            await get_full_tournament_details(conn, TournamentId(flow.id), stage_id=StageId(stage)),
            await get_full_tournament_details(
                conn, TournamentId(flow.id), round_id=RoundId(round_id)
            ),
            await get_full_tournament_details(
                conn,
                TournamentId(flow.id),
                stage_item_ids={StageItemId(group_a)},
                no_draft_rounds=True,
            ),
        ]
        for stages in filtered_results:
            for returned_stage in stages:
                for item in returned_stage.stage_items:
                    inputs = [
                        *item.inputs,
                        *(
                            input_
                            for round_ in item.rounds
                            for match in round_.matches
                            for input_ in (match.stage_item_input1, match.stage_item_input2)
                        ),
                    ]
                    for input_ in inputs:
                        if isinstance(input_, StageItemInputFinal):
                            expected = ordinary[input_.team.name]
                            for key in ("wins", "draws", "losses", "elo_score", "swiss_score"):
                                assert getattr(input_.team, key) == (
                                    Decimal(expected[key])
                                    if key.endswith("score")
                                    else expected[key]
                                )
                    assert all(input_.wins <= 1 for input_ in item.inputs)
