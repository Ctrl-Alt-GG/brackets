"""API contract snapshots for a tournament with groups, playoffs and draft Swiss pairings."""

import json
import random
from collections.abc import Iterator
from contextlib import contextmanager
from functools import partial
from http import HTTPMethod
from itertools import product
from pathlib import Path
from time import perf_counter
from typing import Any

import pytest
from sqlalchemy import event, select
from sqlalchemy.ext.asyncio import AsyncSession

from bracket import orm
from bracket.database import engine
from bracket.logic.scheduling.swiss import get_swiss_pairing
from bracket.sql.rounds import get_next_round_name
from bracket.sql.stages import get_full_tournament_details
from bracket.utils.id_types import RoundId, StageId, StageItemId, TournamentId
from tests.integration_tests.api.flows import api_tournament
from tests.integration_tests.api.shared import SUCCESS_RESPONSE, send_auth_request
from tests.integration_tests.models import AuthContext
from tests.integration_tests.snapshots import canonical_tournament

GOLDEN = Path(__file__).parents[1] / "assets" / "golden" / "tournament.json"


@contextmanager
def measured() -> Iterator[dict[str, float]]:
    measurements = {"queries": 0.0}

    def count(*_: Any) -> None:
        measurements["queries"] += 1

    event.listen(engine.sync_engine, "before_cursor_execute", count)
    start = perf_counter()
    try:
        yield measurements
    finally:
        measurements["seconds"] = perf_counter() - start
        event.remove(engine.sync_engine, "before_cursor_execute", count)


@pytest.mark.asyncio(loop_scope="session")
async def test_tournament_contract(
    startup_and_shutdown_uvicorn_server: None,
    auth_context: AuthContext,
    request: pytest.FixtureRequest,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        "bracket.routes.rounds.get_swiss_pairing",
        partial(get_swiss_pairing, rng=random.Random(0)),
    )
    async with api_tournament(auth_context, "ORM contract") as flow:
        teams = await flow.add_teams("Alpha, Alice", "Bravo, Bob", "Charlie, Cara", "Delta")
        group_stage = await flow.add_stage()
        group = await flow.add_stage_item(group_stage, "ROUND_ROBIN", 4, "Group")
        playoff_stage = await flow.add_stage()
        knockout = await flow.add_stage_item(playoff_stage, "SINGLE_ELIMINATION", 4, "Playoffs")
        swiss = await flow.add_stage_item(playoff_stage, "SWISS", 4, "Swiss")
        future_stage = await flow.add_stage()
        future = await flow.add_stage_item(future_stage, "SWISS", 2, "Future")
        await flow.add_stage_item(future_stage, "SWISS", 2, "Empty")
        await flow.add_stage()
        await flow.fill(group, *teams.values())
        await flow.feed(knockout, group, 1, 2, 3, 4)
        await flow.feed(swiss, group, 1, 2, 3, 4)
        await flow.feed(future, group, 1)
        assert await flow.activate() == SUCCESS_RESPONSE
        for matches in await flow.matches(group):
            for index, match in enumerate(matches):
                await flow.score(match, 3, index)
        with measured() as activation:
            assert await flow.activate() == SUCCESS_RESPONSE
        assert (
            await flow.call(HTTPMethod.POST, "rounds", {"stage_item_id": swiss}) == SUCCESS_RESPONSE
        )
        semi = (await flow.matches(knockout))[0][0]
        with measured() as score:
            await flow.score(semi, 2, 0)
        # Empty result and nullable options exercise serialization in both directions.
        with measured() as details:
            detail_response = await flow.call(HTTPMethod.GET, "details")
        endpoints = ["stages?no_draft_rounds=false", "teams", "players", "standings", "rankings"]
        actual = {"details": detail_response}
        for endpoint in endpoints:
            actual[endpoint] = await flow.call(HTTPMethod.GET, endpoint)
        listing = await send_auth_request(HTTPMethod.GET, "tournaments?filter_=ALL", auth_context)
        listing["data"] = [item for item in listing["data"] if item["id"] == flow.id]
        actual["tournaments?filter_=ALL"] = listing
        for name, result in (("activation", activation), ("score", score), ("details", details)):
            request.node.user_properties.append((name, json.dumps(result)))
            # A fixed fixture catches repeated graph loads and queries added per stage item.
            assert result["queries"] <= {"activation": 20, "score": 14, "details": 15}[name]
        actual = canonical_tournament(actual, club_id=auth_context.club.id)
        assert actual == json.loads(GOLDEN.read_text())
        await assert_stage_filters(TournamentId(flow.id))


async def assert_stage_filters(tournament_id: TournamentId) -> None:
    async with AsyncSession(engine, expire_on_commit=False) as session:
        # Keep entities alive so filtered eager loads must replace already loaded collections.
        entities = (
            await session.scalars(select(orm.Stage).where(orm.Stage.tournament_id == tournament_id))
        ).all()
        complete = await get_full_tournament_details(session, tournament_id)
        selected_item = next(
            item for stage in complete for item in stage.stage_items if item.rounds
        )
        selected_round = selected_item.rounds[0].id
        draft_round = next(
            round_.id
            for stage in complete
            for item in stage.stage_items
            for round_ in item.rounds
            if round_.is_draft
        )
        later_items = {item.id for stage in complete[1:] for item in stage.stage_items}
        for stage_id, item_ids, round_id, no_draft in product(
            (None, complete[0].id, complete[-1].id, StageId(-1)),
            (None, {selected_item.id}, later_items, set()),
            (None, selected_round, draft_round, RoundId(-1)),
            (False, True),
        ):
            expected = [
                stage.model_copy(
                    update={
                        "stage_items": [
                            item.model_copy(
                                update={
                                    "rounds": [
                                        round_
                                        for round_ in item.rounds
                                        if (round_id is None or round_.id == round_id)
                                        and (not no_draft or not round_.is_draft)
                                    ]
                                }
                            )
                            for item in stage.stage_items
                            if item_ids is None or item.id in item_ids
                        ]
                    }
                )
                for stage in complete
                if (stage_id is None or stage.id == stage_id)
                and (item_ids is None or any(item.id in item_ids for item in stage.stage_items))
            ]
            assert (
                await get_full_tournament_details(
                    session,
                    tournament_id,
                    stage_id=stage_id,
                    stage_item_ids=item_ids,
                    round_id=round_id,
                    no_draft_rounds=no_draft,
                )
                == expected
            )
        assert await get_full_tournament_details(session, tournament_id) == complete
        assert len(entities) == len(complete)
        # A stored round and stage item can exist without their child collections.
        empty_item = orm.StageItem(
            tournament_id=tournament_id,
            stage_id=complete[-1].id,
            name="No inputs",
            team_count=2,
            type=selected_item.type,
            ranking_id=selected_item.ranking_id,
        )
        session.add(empty_item)
        await session.flush()
        session.add(
            orm.Round(
                tournament_id=tournament_id,
                stage_item_id=empty_item.id,
                name="Round 09",
                is_draft=False,
            )
        )
        await session.flush()
        stages = await get_full_tournament_details(
            session, tournament_id, stage_item_ids={StageItemId(empty_item.id)}
        )
        assert stages[0].stage_items[0].inputs == []
        assert stages[0].stage_items[0].rounds[0].matches == []
        assert (
            await get_next_round_name(session, tournament_id, StageItemId(empty_item.id))
            == "Round 10"
        )
        assert (
            await get_next_round_name(session, TournamentId(-1), StageItemId(empty_item.id))
            == "Round 01"
        )
