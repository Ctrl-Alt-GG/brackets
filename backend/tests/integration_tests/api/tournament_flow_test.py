from datetime import timedelta
from http import HTTPMethod

import pytest

from tests.integration_tests.api.flows import api_tournament, names, parse_time, result
from tests.integration_tests.api.shared import SUCCESS_RESPONSE
from tests.integration_tests.models import AuthContext


@pytest.mark.asyncio(loop_scope="session")
async def test_open_group_slot_keeps_the_workspace_usable(
    startup_and_shutdown_uvicorn_server: None, auth_context: AuthContext
) -> None:
    """
    A final that takes "#4 of the group" while the group has an open slot can't be decided yet.
    The workspace loads this on every page, so it must still answer, and say what is wrong when
    the organizer tries to start the final.
    """
    async with api_tournament(auth_context) as flow:
        teams = await flow.add_teams("Alpha", "Bravo", "Charlie", "Delta")
        group = await flow.add_stage_item(await flow.add_stage(), "ROUND_ROBIN", 4, "Group")
        final = await flow.add_stage_item(await flow.add_stage(), "SINGLE_ELIMINATION", 2, "Final")
        await flow.fill(group, teams["Alpha"], teams["Bravo"], teams["Charlie"])
        await flow.feed(final, group, 1, 4)
        await flow.activate()

        preview = await flow.call(HTTPMethod.GET, "next_stage_rankings")
        activation = await flow.activate()

        await flow.set_slot(group, 4, {"team_id": teams["Delta"]})
        preview_when_filled = await flow.call(HTTPMethod.GET, "next_stage_rankings")

    # Only the slot that can be decided is in the preview.
    assert [update["stage_item_input"]["slot"] for update in preview["data"][str(final)]] == [1]
    assert activation == {
        "detail": (
            "Slot 2 of Final takes #4 of Group, which doesn't have that many teams. Assign the "
            "missing teams in the current stage, or change the slot."
        )
    }
    assert len(preview_when_filled["data"][str(final)]) == 2


@pytest.mark.asyncio(loop_scope="session")
async def test_going_back_a_stage_asks_before_discarding_results(
    startup_and_shutdown_uvicorn_server: None, auth_context: AuthContext
) -> None:
    async with api_tournament(auth_context) as flow:
        teams = await flow.add_teams("Alpha", "Bravo", "Charlie", "Delta")
        group = await flow.add_stage_item(await flow.add_stage(), "ROUND_ROBIN", 4, "Group")
        bracket = await flow.add_stage_item(
            await flow.add_stage(), "SINGLE_ELIMINATION", 4, "Playoffs"
        )
        await flow.fill(group, *teams.values())
        await flow.feed(bracket, group, 1, 2, 3, 4)
        await flow.activate()
        for round_matches in await flow.matches(group):
            for index, match in enumerate(round_matches):
                await flow.score(match, 2, 1 if index == 0 else 0)
        await flow.activate()
        semi_finals, _ = await flow.matches(bracket)
        for match in semi_finals:
            await flow.score(match, 3, 1)
        played = await flow.matches(bracket)

        refused = await flow.activate("previous")
        after_refusal = await flow.matches(bracket)

        confirmed = await flow.activate("previous", discard_results=True)
        cleared = await flow.matches(bracket)

    assert all(name is not None for name in names(played[1][0]))
    assert refused == {
        "detail": (
            "Going back discards the 2 results of Stage. Confirm that they can be discarded."
        )
    }
    assert [result(match) for match in after_refusal[0]] == [(3, 1), (3, 1)]

    assert confirmed == SUCCESS_RESPONSE
    assert [result(match) for match in cleared[0]] == [(0, 0), (0, 0)]
    # The teams that had advanced are released, also from the final they had reached.
    assert [names(match) for match in cleared[0]] == [(None, None), (None, None)]
    assert cleared[1][0]["stage_item_input1_id"] is None
    assert cleared[1][0]["stage_item_input2_id"] is None


@pytest.mark.asyncio(loop_scope="session")
async def test_going_back_resets_swiss_ratings_in_released_slots(
    startup_and_shutdown_uvicorn_server: None, auth_context: AuthContext
) -> None:
    async with api_tournament(auth_context) as flow:
        teams = await flow.add_teams("Alpha", "Bravo")
        group = await flow.add_stage_item(await flow.add_stage(), "ROUND_ROBIN", 2, "Group")
        swiss = await flow.add_stage_item(await flow.add_stage(), "SWISS", 2, "Swiss")
        await flow.fill(group, *teams.values())
        await flow.feed(swiss, group, 1, 2)
        await flow.activate()
        await flow.score((await flow.matches(group))[0][0], 2, 0)
        await flow.activate()
        await flow.call(HTTPMethod.POST, "rounds", {"stage_item_id": swiss})
        round_ = (await flow.stage_item(swiss))["rounds"][0]
        await flow.call(
            HTTPMethod.PUT, f"rounds/{round_['id']}", {"name": round_["name"], "is_draft": False}
        )
        await flow.score((await flow.matches(swiss))[0][0], 2, 0)
        rated = (await flow.stage_item(swiss))["inputs"]

        await flow.activate("previous", discard_results=True)
        released = (await flow.stage_item(swiss))["inputs"]
        await flow.activate()
        reactivated = (await flow.stage_item(swiss))["inputs"]

    assert sorted(float(input_["points"]) for input_ in rated) == [1184, 1216]
    assert all(input_["team_id"] is None for input_ in released)
    for inputs in (released, reactivated):
        assert all(float(input_["points"]) == 1200 for input_ in inputs)
        assert all(input_["wins"] == input_["draws"] == input_["losses"] == 0 for input_ in inputs)


@pytest.mark.asyncio(loop_scope="session")
async def test_correcting_a_knockout_result_discards_what_followed_from_it(
    startup_and_shutdown_uvicorn_server: None, auth_context: AuthContext
) -> None:
    async with api_tournament(auth_context) as flow:
        teams = await flow.add_teams("A", "B", "C", "D")
        bracket = await flow.add_stage_item(
            await flow.add_stage(), "SINGLE_ELIMINATION", 4, "Bracket"
        )
        await flow.fill(bracket, *teams.values())
        await flow.activate()
        (semi_final1, semi_final2), (final,) = await flow.matches(bracket)
        await flow.score(semi_final1, 2, 0)
        await flow.score(semi_final2, 2, 0)
        await flow.score((await flow.matches(bracket))[1][0], 3, 1)

        # The same winner with another score changes nothing further down.
        await flow.score(semi_final1, 5, 4)
        final_after_same_winner = (await flow.matches(bracket))[1][0]

        await flow.score(semi_final1, 0, 2)
        final_after_other_winner = (await flow.matches(bracket))[1][0]

        draw = await flow.score(semi_final2, 1, 1)
        scoreless = await flow.score(semi_final2, 0, 0, scoreless_result=True)
        too_high = await flow.score(semi_final2, 100_001, 0)
        # A score never moves a match: the round in the body, if any, is ignored.
        await flow.score(semi_final2, 2, 0, round_id=final["round_id"])
        rounds = await flow.matches(bracket)

    assert names(final_after_same_winner) == ("A", "C")
    assert result(final_after_same_winner) == (3, 1)

    assert names(final_after_other_winner) == ("B", "C")
    assert result(final_after_other_winner) == (0, 0)
    assert final_after_other_winner["played"] is False

    knockout_needs_winner = {
        "detail": "A knockout match needs a winner. Enter the score after overtime or the tiebreak."
    }
    assert draw == knockout_needs_winner
    assert scoreless == knockout_needs_winner
    assert too_high["detail"][0]["loc"] == ["body", "stage_item_input1_score"]
    assert [len(round_matches) for round_matches in rounds] == [2, 1]


@pytest.mark.asyncio(loop_scope="session")
async def test_deleting_a_stage_item_opens_the_slots_it_fed(
    startup_and_shutdown_uvicorn_server: None, auth_context: AuthContext
) -> None:
    async with api_tournament(auth_context) as flow:
        teams = await flow.add_teams("Alpha", "Bravo", "Charlie", "Delta")
        group = await flow.add_stage_item(await flow.add_stage(), "ROUND_ROBIN", 4, "Group")
        final_stage = await flow.add_stage()
        final = await flow.add_stage_item(final_stage, "SINGLE_ELIMINATION", 2, "Final")
        await flow.fill(group, *teams.values())
        await flow.feed(final, group, 1, 2)
        await flow.activate()
        for round_matches in await flow.matches(group):
            for match in round_matches:
                await flow.score(match, 2, 0)
        await flow.activate()
        await flow.score((await flow.matches(final))[0][0], 2, 1)

        with_results = await flow.call(HTTPMethod.DELETE, f"stage_items/{group}")

        await flow.call(HTTPMethod.DELETE, f"stage_items/{final}")
        swiss = await flow.add_stage_item(final_stage, "SWISS", 4, "Swiss finals")
        await flow.feed(swiss, group, 1, 2, 3, 4)
        without_results = await flow.call(HTTPMethod.DELETE, f"stage_items/{group}")
        swiss_inputs = (await flow.stage_item(swiss))["inputs"]

    assert with_results == {
        "detail": "Final takes teams from this stage item and already has results. Delete it first."
    }
    assert without_results == SUCCESS_RESPONSE
    # The slots stay, and are open again.
    assert [input_["slot"] for input_ in swiss_inputs] == [1, 2, 3, 4]
    assert all(
        input_["team_id"] is None and input_["winner_from_stage_item_id"] is None
        for input_ in swiss_inputs
    )


@pytest.mark.asyncio(loop_scope="session")
async def test_goalless_result_counts_as_played(
    startup_and_shutdown_uvicorn_server: None, auth_context: AuthContext
) -> None:
    """0-0 normally reads as "not played yet". A match that ended 0-0 can be recorded as such."""
    async with api_tournament(auth_context) as flow:
        teams = await flow.add_teams("Alpha", "Bravo")
        group = await flow.add_stage_item(await flow.add_stage(), "ROUND_ROBIN", 2, "Group")
        await flow.fill(group, *teams.values())
        await flow.activate()
        match = (await flow.matches(group))[0][0]

        await flow.score(match, 0, 0)
        unplayed = (await flow.matches(group))[0][0]
        progress_unplayed = await flow.tournament()

        await flow.score(match, 0, 0, scoreless_result=True)
        played = (await flow.matches(group))[0][0]
        standings = (await flow.call(HTTPMethod.GET, "standings"))["data"][str(group)]
        progress_played = await flow.tournament()

        # A score is a result by itself, so the marker isn't kept next to one.
        await flow.score(match, 1, 0, scoreless_result=True)
        scored = (await flow.matches(group))[0][0]

    assert unplayed["played"] is False
    assert (progress_unplayed["matches_total"], progress_unplayed["matches_played"]) == (1, 0)
    assert played["played"] is True
    assert [(standing["draws"], standing["wins"]) for standing in standings] == [(1, 0), (1, 0)]
    assert (progress_played["matches_total"], progress_played["matches_played"]) == (1, 1)
    assert progress_played["last_match_end"] == "2030-06-01T10:35:00Z"
    assert (scored["played"], scored["scoreless_result"]) == (True, False)


@pytest.mark.asyncio(loop_scope="session")
async def test_delaying_the_schedule_moves_what_is_still_to_be_played(
    startup_and_shutdown_uvicorn_server: None, auth_context: AuthContext
) -> None:
    async with api_tournament(auth_context) as flow:
        teams = await flow.add_teams("Alpha", "Bravo", "Charlie", "Delta")
        group = await flow.add_stage_item(await flow.add_stage(), "ROUND_ROBIN", 4, "Group")
        final = await flow.add_stage_item(await flow.add_stage(), "SINGLE_ELIMINATION", 2, "Final")
        await flow.fill(group, *teams.values())
        await flow.feed(final, group, 1, 2)

        def starts(rounds: list[list[dict]]) -> list:  # type: ignore[type-arg]
            return [parse_time(round_matches[0]["start_time"]) for round_matches in rounds]

        planned = starts(await flow.matches(group)) + starts(await flow.matches(final))

        # Nothing has been played: the tournament itself starts later.
        await flow.call(HTTPMethod.POST, "delay_schedule", {"minutes": 20})
        all_delayed = starts(await flow.matches(group)) + starts(await flow.matches(final))
        tournament_start = parse_time((await flow.tournament())["start_time"])

        await flow.activate()
        for match in (await flow.matches(group))[0]:
            await flow.score(match, 2, 0)
        # The first round is played: the rounds after it move, and the final with them.
        await flow.call(HTTPMethod.POST, "delay_schedule", {"minutes": 15})
        rest_delayed = starts(await flow.matches(group)) + starts(await flow.matches(final))

        for round_matches in (await flow.matches(group))[1:]:
            for match in round_matches:
                await flow.score(match, 2, 0)
        # Only the final is left, which starts when the group ends.
        await flow.call(HTTPMethod.POST, "delay_schedule", {"minutes": 10})
        final_delayed = starts(await flow.matches(group)) + starts(await flow.matches(final))

        await flow.activate()
        await flow.score((await flow.matches(final))[0][0], 2, 1)
        nothing_left = await flow.call(HTTPMethod.POST, "delay_schedule", {"minutes": 10})
        zero = await flow.call(HTTPMethod.POST, "delay_schedule", {"minutes": 0})

    def moved(by: list[int]) -> list:  # type: ignore[type-arg]
        return [start + timedelta(minutes=minutes) for start, minutes in zip(planned, by)]

    assert all_delayed == moved([20, 20, 20, 20])
    assert tournament_start == planned[0] + timedelta(minutes=20)
    assert rest_delayed == moved([20, 35, 35, 35])
    assert final_delayed == moved([20, 35, 35, 45])
    assert nothing_left == {
        "detail": "Every round has started already, so there is nothing left to move"
    }
    assert zero["detail"][0]["msg"].endswith("Enter how many minutes to move the schedule by")


@pytest.mark.asyncio(loop_scope="session")
async def test_moving_remaining_rounds_earlier_requires_enough_break_time(
    startup_and_shutdown_uvicorn_server: None, auth_context: AuthContext
) -> None:
    async with api_tournament(auth_context) as flow:
        teams = await flow.add_teams("A", "B", "C", "D")
        group = await flow.add_stage_item(await flow.add_stage(), "ROUND_ROBIN", 4, "Group")
        await flow.fill(group, *teams.values())
        for match in (await flow.matches(group))[0]:
            await flow.score(match, 2, 0)
        planned = await flow.matches(group)

        refused = await flow.call(HTTPMethod.POST, "delay_schedule", {"minutes": -15})
        after_refusal = await flow.matches(group)
        accepted = await flow.call(HTTPMethod.POST, "delay_schedule", {"minutes": -5})
        moved = await flow.matches(group)

    assert refused == {
        "detail": (
            "The remaining rounds can move earlier by at most 5 minutes without overlapping "
            "the previous round."
        )
    }
    assert after_refusal == planned
    assert accepted == SUCCESS_RESPONSE
    assert moved[0][0]["start_time"] == planned[0][0]["start_time"]
    assert all(
        parse_time(after[0]["start_time"])
        == parse_time(before[0]["start_time"]) - timedelta(minutes=5)
        for before, after in zip(planned[1:], moved[1:])
    )


@pytest.mark.asyncio(loop_scope="session")
async def test_delaying_the_schedule_leaves_the_round_being_played(
    startup_and_shutdown_uvicorn_server: None, auth_context: AuthContext
) -> None:
    """Groups play side by side: a result in one of them means that round is on in all of them."""
    async with api_tournament(auth_context) as flow:
        teams = list((await flow.add_teams(*(f"Team {number}" for number in range(8)))).values())
        stage = await flow.add_stage()
        group_a = await flow.add_stage_item(stage, "ROUND_ROBIN", 4, "Group A")
        group_b = await flow.add_stage_item(stage, "ROUND_ROBIN", 4, "Group B")
        await flow.fill(group_a, *teams[:4])
        await flow.fill(group_b, *teams[4:])
        await flow.activate()

        async def starts() -> list:  # type: ignore[type-arg]
            return [
                parse_time(round_matches[0]["start_time"])
                for group in (group_a, group_b)
                for round_matches in await flow.matches(group)
            ]

        planned = await starts()
        for group in (group_a, group_b):
            for match in (await flow.matches(group))[0]:
                await flow.score(match, 2, 0)
        # The second round is under way: one match of one group has its result.
        await flow.score((await flow.matches(group_a))[1][0], 1, 0)
        await flow.call(HTTPMethod.POST, "delay_schedule", {"minutes": 15})
        delayed = await starts()

    late = timedelta(minutes=15)
    assert delayed == [
        *planned[:2],
        planned[2] + late,
        *planned[3:5],
        planned[5] + late,
    ]


@pytest.mark.asyncio(loop_scope="session")
async def test_assigning_a_team_to_parallel_groups_updates_schedule_conflicts(
    startup_and_shutdown_uvicorn_server: None, auth_context: AuthContext
) -> None:
    async with api_tournament(auth_context) as flow:
        teams = await flow.add_teams("Alpha", "Bravo", "Charlie", "Delta")
        stage = await flow.add_stage()
        group_a = await flow.add_stage_item(stage, "ROUND_ROBIN", 2, "Group A")
        group_b = await flow.add_stage_item(stage, "ROUND_ROBIN", 2, "Group B")
        await flow.fill(group_a, teams["Alpha"], teams["Bravo"])
        await flow.fill(group_b, teams["Alpha"], teams["Charlie"])
        conflicting = [(await flow.matches(group))[0][0] for group in (group_a, group_b)]

        await flow.set_slot(group_b, 1, {"team_id": teams["Delta"]})
        resolved = [(await flow.matches(group))[0][0] for group in (group_a, group_b)]
        await flow.set_slot(group_b, 1, {"team_id": teams["Alpha"]})
        await flow.call(HTTPMethod.DELETE, f"stage_items/{group_b}")
        after_deletion = (await flow.matches(group_a))[0][0]

    assert all(match["stage_item_input1_conflict"] for match in conflicting)
    assert all(not match["stage_item_input2_conflict"] for match in conflicting)
    assert all(
        not match["stage_item_input1_conflict"] and not match["stage_item_input2_conflict"]
        for match in resolved
    )
    assert not after_deletion["stage_item_input1_conflict"]


@pytest.mark.asyncio(loop_scope="session")
async def test_details_are_one_answer_for_everyone(
    startup_and_shutdown_uvicorn_server: None, auth_context: AuthContext
) -> None:
    async with api_tournament(auth_context) as flow:
        teams = await flow.add_teams("Alpha, Anna, Adam", "Bravo, Bea")
        swiss = await flow.add_stage_item(await flow.add_stage(), "SWISS", 2, "Swiss")
        await flow.fill(swiss, *teams.values())
        await flow.activate()
        await flow.call(HTTPMethod.POST, "rounds", {"name": None, "stage_item_id": swiss})

        details = (await flow.call(HTTPMethod.GET, "details", anonymous=True))["data"]
        visitor = await flow.call(HTTPMethod.GET, "access", anonymous=True)
        organizer = await flow.call(HTTPMethod.GET, "access")

    assert details["tournament"]["id"] == flow.id
    assert sorted(player["name"] for player in details["players"]) == ["Adam", "Anna", "Bea"]
    assert [team["name"] for team in details["teams"]] == ["Alpha", "Bravo"]
    assert len(details["rankings"]) == 1
    assert len(details["standings"][str(swiss)]) == 2
    # The round that was drawn is still a draft, which only organizers see.
    assert details["stages"][0]["stage_items"][0]["rounds"] == []
    assert visitor == {"data": {"can_manage": False}}
    assert organizer == {"data": {"can_manage": True}}


@pytest.mark.asyncio(loop_scope="session")
async def test_player_is_in_one_team_unless_the_tournament_allows_more(
    startup_and_shutdown_uvicorn_server: None, auth_context: AuthContext
) -> None:
    async with api_tournament(auth_context) as flow:
        teams = await flow.add_teams("Alpha, Anna", "Bravo")
        players = (await flow.call(HTTPMethod.GET, "players"))["data"]["players"]
        body = {"name": "Bravo", "active": True, "player_ids": [players[0]["id"]]}

        refused = await flow.call(HTTPMethod.PUT, f"teams/{teams['Bravo']}", body)
        free_players = await flow.call(HTTPMethod.GET, "players?not_in_team=true")

        settings = await flow.tournament()
        await flow.call(
            HTTPMethod.PUT,
            "",
            {
                key: settings[key]
                for key in (
                    "name",
                    "start_time",
                    "dashboard_public",
                    "dashboard_endpoint",
                    "duration_minutes",
                    "margin_minutes",
                )
            }
            | {"players_can_be_in_multiple_teams": True},
        )
        allowed = await flow.call(HTTPMethod.PUT, f"teams/{teams['Bravo']}", body)

    assert refused == {
        "detail": (
            "Anna is already in Alpha. Players can be in one team, unless the tournament's "
            "settings allow more."
        )
    }
    assert free_players["data"] == {"count": 0, "players": []}
    assert allowed["data"]["name"] == "Bravo"


@pytest.mark.asyncio(loop_scope="session")
async def test_tournament_keeps_a_ranking_and_brackets_a_power_of_two(
    startup_and_shutdown_uvicorn_server: None, auth_context: AuthContext
) -> None:
    async with api_tournament(auth_context) as flow:
        ranking = (await flow.call(HTTPMethod.GET, "rankings"))["data"][0]
        last_ranking = await flow.call(HTTPMethod.DELETE, f"rankings/{ranking['id']}")

        six_teams = await flow.call(
            HTTPMethod.POST,
            "stage_items",
            {
                "stage_id": await flow.add_stage(),
                "name": "Bracket",
                "type": "SINGLE_ELIMINATION",
                "team_count": 6,
                "ranking_id": None,
            },
        )

    assert last_ranking == {"detail": "A tournament needs at least one ranking"}
    assert six_teams["detail"][0]["msg"].endswith(
        "A single elimination bracket has 2, 4, 8, 16, 32 teams"
    )
