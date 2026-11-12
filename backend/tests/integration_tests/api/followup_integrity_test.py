import asyncio
from http import HTTPMethod
from unittest.mock import patch

import pytest

from bracket.routes import rounds as round_routes
from bracket.sql.matches import sql_create_match
from tests.integration_tests.api.flows import api_tournament, names, result
from tests.integration_tests.api.shared import SUCCESS_RESPONSE
from tests.integration_tests.models import AuthContext


@pytest.mark.asyncio(loop_scope="session")
@pytest.mark.parametrize("format_", ["ROUND_ROBIN", "SWISS", "SINGLE_ELIMINATION"])
async def test_replacing_a_scored_team_requires_clearing_its_results(
    startup_and_shutdown_uvicorn_server: None, auth_context: AuthContext, format_: str
) -> None:
    async with api_tournament(auth_context) as flow:
        teams = await flow.add_teams("A", "B", "C", "D", "Replacement")
        item = await flow.add_stage_item(await flow.add_stage(), format_, 4, "Group")
        await flow.fill(item, teams["A"], teams["B"], teams["C"], teams["D"])
        if format_ == "SWISS":
            await flow.call(HTTPMethod.POST, "rounds", {"stage_item_id": item})
            round_ = (await flow.stage_item(item))["rounds"][0]
            await flow.call(
                HTTPMethod.PUT, f"rounds/{round_['id']}", {"name": "Round", "is_draft": False}
            )
        first = next(match for match in (await flow.matches(item))[0] if "A" in names(match))
        if format_ == "SINGLE_ELIMINATION":
            for match in (await flow.matches(item))[0]:
                await flow.score(match, 2, 0)
            await flow.score((await flow.matches(item))[1][0], 3, 1)
        else:
            await flow.score(first, 0, 0, scoreless_result=True)
        before = await flow.stage_item(item)

        refused = await flow.set_slot(item, 1, {"team_id": teams["Replacement"]})
        noop = await flow.set_slot(item, 1, {"team_id": teams["A"]})
        unchanged = await flow.stage_item(item)

        await flow.score(first, 0, 0)
        accepted = await flow.set_slot(item, 1, {"team_id": teams["Replacement"]})
        changed = await flow.stage_item(item)

    assert "Clear this team's match results" in refused["detail"]
    assert noop == SUCCESS_RESPONSE
    assert unchanged == before
    assert accepted == SUCCESS_RESPONSE
    assert changed["inputs"][0]["team_id"] == teams["Replacement"]
    assert all(
        not match["played"]
        for round_ in changed["rounds"]
        for match in round_["matches"]
        if teams["Replacement"]
        in (
            (match["stage_item_input1"] or {}).get("team_id"),
            (match["stage_item_input2"] or {}).get("team_id"),
        )
    )
    if format_ == "SINGLE_ELIMINATION":
        assert result(changed["rounds"][1]["matches"][0]) == (0, 0)


@pytest.mark.asyncio(loop_scope="session")
async def test_slots_and_swiss_competitors_must_belong_to_their_parent(
    startup_and_shutdown_uvicorn_server: None, auth_context: AuthContext
) -> None:
    async with api_tournament(auth_context) as flow:
        teams = await flow.add_teams("A", "B", "C", "D")
        stage = await flow.add_stage()
        group = await flow.add_stage_item(stage, "ROUND_ROBIN", 2, "Group")
        swiss = await flow.add_stage_item(stage, "SWISS", 2, "Swiss")
        await flow.fill(group, teams["A"], teams["B"])
        await flow.fill(swiss, teams["C"], teams["D"])
        original = await flow.stage_item(group)
        group_slots = [input_["id"] for input_ in original["inputs"]]

        wrong_parent = await flow.call(
            HTTPMethod.PUT, f"stage_items/{swiss}/inputs/{group_slots[0]}", {"team_id": teams["D"]}
        )
        assert await flow.stage_item(group) == original

        await flow.call(HTTPMethod.POST, "rounds", {"stage_item_id": swiss})
        round_ = (await flow.stage_item(swiss))["rounds"][0]
        for match in round_["matches"]:
            await flow.call(HTTPMethod.DELETE, f"matches/{match['id']}")
        foreign_match = await flow.call(
            HTTPMethod.POST,
            "matches",
            {
                "round_id": round_["id"],
                "stage_item_input1_id": group_slots[0],
                "stage_item_input2_id": group_slots[1],
            },
        )
        local = (await flow.stage_item(swiss))["inputs"]
        local_match = await flow.call(
            HTTPMethod.POST,
            "matches",
            {
                "round_id": round_["id"],
                "stage_item_input1_id": local[0]["id"],
                "stage_item_input2_id": local[1]["id"],
            },
        )

    assert wrong_parent == {"detail": "Could not find the stage item input"}
    assert foreign_match == {"detail": "Choose two assigned teams from this round's stage item"}
    assert "data" in local_match


@pytest.mark.asyncio(loop_scope="session")
async def test_advancement_sources_require_an_earlier_group_and_valid_position(
    startup_and_shutdown_uvicorn_server: None, auth_context: AuthContext
) -> None:
    async with api_tournament(auth_context) as flow:
        stage1 = await flow.add_stage()
        group = await flow.add_stage_item(stage1, "ROUND_ROBIN", 2, "Group")
        knockout = await flow.add_stage_item(stage1, "SINGLE_ELIMINATION", 2, "Knockout")
        later = await flow.add_stage_item(await flow.add_stage(), "SWISS", 2, "Later")
        responses = [
            await flow.set_slot(
                target, 1, {"winner_from_stage_item_id": source, "winner_position": position}
            )
            for target, source, position in (
                (group, group, 1),
                (group, later, 1),
                (later, knockout, 1),
                (later, group, 3),
                (later, group, 2),
            )
        ]

    assert all("earlier stage" in response["detail"] for response in responses[:3])
    assert "doesn't have that many team slots" in responses[3]["detail"]
    assert responses[4] == SUCCESS_RESPONSE


@pytest.mark.asyncio(loop_scope="session")
async def test_regeneration_keeps_the_draft_when_pairing_or_inserting_fails(
    startup_and_shutdown_uvicorn_server: None, auth_context: AuthContext
) -> None:
    async with api_tournament(auth_context) as flow:
        teams = await flow.add_teams("A", "B")
        item = await flow.add_stage_item(await flow.add_stage(), "SWISS", 2, "Swiss")
        await flow.fill(item, *teams.values())
        await flow.call(HTTPMethod.POST, "rounds", {"stage_item_id": item, "name": "My draft"})
        before = (await flow.stage_item(item))["rounds"][0]
        endpoint = f"rounds/{before['id']}/regenerate"

        await flow.call(
            HTTPMethod.PUT, f"teams/{teams['B']}", {"name": "B", "active": False, "player_ids": []}
        )
        invalid = await flow.call(HTTPMethod.POST, endpoint)
        retained = (await flow.stage_item(item))["rounds"][0]
        assert retained["id"] == before["id"] and retained["name"] == before["name"]
        assert [match["id"] for match in retained["matches"]] == [
            match["id"] for match in before["matches"]
        ]
        assert [names(match) for match in retained["matches"]] == [
            names(match) for match in before["matches"]
        ]
        await flow.call(
            HTTPMethod.PUT, f"teams/{teams['B']}", {"name": "B", "active": True, "player_ids": []}
        )

        async def fail_after_insert(*args, **kwargs):  # type: ignore[no-untyped-def]
            await sql_create_match(*args, **kwargs)
            raise RuntimeError("Injected replacement failure")

        with patch.object(round_routes, "sql_create_match", side_effect=fail_after_insert):
            failed = await flow.call(HTTPMethod.POST, endpoint)
        assert (await flow.stage_item(item))["rounds"][0] == before
        accepted = await flow.call(HTTPMethod.POST, endpoint)
        after = (await flow.stage_item(item))["rounds"][0]

        await flow.score(after["matches"][0], 1, 0)
        scored = await flow.call(HTTPMethod.POST, endpoint)
        await flow.call(
            HTTPMethod.PUT, f"rounds/{before['id']}", {"name": "My draft", "is_draft": False}
        )
        published = await flow.call(HTTPMethod.POST, endpoint)

    assert invalid == {"detail": "No replacement pairings are available. The draft was kept."}
    assert failed == {"detail": "Internal server error"}
    assert accepted == SUCCESS_RESPONSE
    assert after["id"] == before["id"] and after["name"] == "My draft"
    assert after["matches"][0]["id"] != before["matches"][0]["id"]
    assert scored == {"detail": "Clear the draft's results before regenerating its pairings"}
    assert published == {"detail": "Only a draft Swiss round can be regenerated"}


@pytest.mark.asyncio(loop_scope="session")
async def test_concurrent_swiss_generation_leaves_one_draft(
    startup_and_shutdown_uvicorn_server: None, auth_context: AuthContext
) -> None:
    async with api_tournament(auth_context) as flow:
        teams = await flow.add_teams("A", "B")
        item = await flow.add_stage_item(await flow.add_stage(), "SWISS", 2, "Swiss")
        await flow.fill(item, *teams.values())
        responses = await asyncio.gather(
            *(flow.call(HTTPMethod.POST, "rounds", {"stage_item_id": item}) for _ in range(2))
        )
        drafts = (await flow.stage_item(item))["rounds"]

    assert responses.count(SUCCESS_RESPONSE) == 1
    assert len(drafts) == 1 and drafts[0]["is_draft"]
