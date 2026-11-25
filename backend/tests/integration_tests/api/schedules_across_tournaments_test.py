"""
Teams and players can take part in several tournaments at once, but play one match at a time.
A tournament's schedule makes room for what they play elsewhere, and shows what still clashes.
"""

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from datetime import datetime, timedelta
from http import HTTPMethod

import pytest
from sqlalchemy import update
from sqlalchemy.ext.asyncio import AsyncSession

from bracket import orm
from bracket.database import engine
from bracket.utils.types import JsonDict
from tests.integration_tests.api.flows import TournamentFlow, api_tournament, parse_time
from tests.integration_tests.models import AuthContext

pytestmark = pytest.mark.asyncio(loop_scope="session")

# When both flows' tournaments start, and how long a match takes with its break.
START = datetime.fromisoformat("2030-06-01T10:00:00+00:00")
MATCH = timedelta(minutes=35)


@asynccontextmanager
async def two_tournaments(
    auth_context: AuthContext,
) -> AsyncIterator[tuple[TournamentFlow, TournamentFlow]]:
    async with (
        api_tournament(auth_context, "First cup") as first,
        api_tournament(auth_context, "Second cup") as second,
    ):
        yield first, second


async def only_match(flow: TournamentFlow, *team_ids: int) -> JsonDict:
    """A group of these two teams, and its one match."""
    group = await flow.add_stage_item(await flow.add_stage(), "ROUND_ROBIN", 2, "Group")
    await flow.fill(group, *team_ids)
    [[match]] = await flow.matches(group)
    return match


async def test_a_match_waits_for_a_team_that_plays_in_another_tournament(
    startup_and_shutdown_uvicorn_server: None, auth_context: AuthContext
) -> None:
    async with two_tournaments(auth_context) as (first, second):
        teams = await first.add_teams("Alpha", "Bravo")
        first_match = await only_match(first, teams["Alpha"], teams["Bravo"])
        charlie = (await second.add_teams("Charlie"))["Charlie"]
        await second.join(teams["Alpha"])
        second_match = await only_match(second, teams["Alpha"], charlie)

    assert parse_time(first_match["start_time"]) == START
    assert parse_time(second_match["start_time"]) == START + MATCH


async def test_a_match_waits_for_a_player_who_plays_for_another_team_elsewhere(
    startup_and_shutdown_uvicorn_server: None, auth_context: AuthContext
) -> None:
    """Alex plays for Alpha in one tournament and for Delta in the other: the same player."""
    async with two_tournaments(auth_context) as (first, second):
        first_teams = await first.add_teams("Alpha,Alex", "Bravo")
        first_match = await only_match(first, *first_teams.values())
        second_teams = await second.add_teams("Delta,alex", "Echo")
        second_match = await only_match(second, *second_teams.values())

    assert parse_time(first_match["start_time"]) == START
    assert parse_time(second_match["start_time"]) == START + MATCH


async def test_a_new_member_who_plays_elsewhere_moves_the_teams_matches(
    startup_and_shutdown_uvicorn_server: None, auth_context: AuthContext
) -> None:
    async with two_tournaments(auth_context) as (first, second):
        first_teams = await first.add_teams("Alpha,Alex", "Bravo")
        await only_match(first, *first_teams.values())
        second_teams = await second.add_teams("Delta", "Echo")
        before = await only_match(second, *second_teams.values())
        [alex] = (await first.call(HTTPMethod.GET, "players"))["data"]["players"]

        await second.call_shared(
            HTTPMethod.PUT,
            f"teams/{second_teams['Delta']}",
            {"name": "Delta", "members": [{"player_id": alex["id"]}]},
        )
        [[after]] = [
            round_["matches"]
            for stage in await second.stages()
            for item in stage["stage_items"]
            for round_ in item["rounds"]
        ]

    assert parse_time(before["start_time"]) == START
    assert parse_time(after["start_time"]) == START + MATCH


async def test_a_clash_between_tournaments_is_shown_until_the_schedule_is_planned_again(
    startup_and_shutdown_uvicorn_server: None, auth_context: AuthContext
) -> None:
    """Two organizers planned at the same moment, so both matches landed at the same time."""
    async with two_tournaments(auth_context) as (first, second):
        teams = await first.add_teams("Alpha", "Bravo")
        first_match = await only_match(first, teams["Alpha"], teams["Bravo"])
        charlie = (await second.add_teams("Charlie"))["Charlie"]
        await second.join(teams["Alpha"])
        second_match = await only_match(second, teams["Alpha"], charlie)
        async with AsyncSession(engine) as session, session.begin():
            await session.execute(
                update(orm.Match).where(orm.Match.id == second_match["id"]).values(start_time=START)
            )

        clashing = await second.conflicts()
        seen_from_the_first = await first.conflicts()
        await second.call(HTTPMethod.POST, "schedule_matches")
        planned_again = await second.conflicts()

    assert clashing == [
        {
            "match_id": second_match["id"],
            "team_id": teams["Alpha"],
            "player_ids": [],
            "other_match_id": first_match["id"],
            "other_tournament_id": first.id,
            "other_tournament_name": "First cup",
        }
    ]
    assert [conflict["other_tournament_name"] for conflict in seen_from_the_first] == ["Second cup"]
    assert planned_again == []


async def test_an_archived_tournament_keeps_its_lineup_until_it_is_reopened(
    startup_and_shutdown_uvicorn_server: None, auth_context: AuthContext
) -> None:
    async with api_tournament(auth_context, "First cup") as flow:
        teams = await flow.add_teams("Alpha,Alex", "Bravo,Ben")
        players = {
            player["name"]: player["id"]
            for player in (await flow.call(HTTPMethod.GET, "players"))["data"]["players"]
        }

        async def roster(*members: JsonDict) -> JsonDict:
            return await flow.call_shared(
                HTTPMethod.PUT, f"teams/{teams['Alpha']}", {"name": "Alpha", "members": members}
            )

        async def change_status(status: str) -> JsonDict:
            return await flow.call(HTTPMethod.POST, "change-status", {"status": status})

        async def lineup() -> list[tuple[str, int]]:
            players = (await flow.call(HTTPMethod.GET, "players"))["data"]["players"]
            return [(player["name"], player["team_id"]) for player in players]

        await change_status("ARCHIVED")
        # Archived tournaments don't stop Ben from being active in both teams.
        changed = await roster(
            {"player_id": players["Alex"], "active": False}, {"player_id": players["Ben"]}
        )
        archived = await lineup()
        clashing = await change_status("OPEN")
        await roster({"player_id": players["Alex"], "active": False})
        reopened = await change_status("OPEN")
        followed = await lineup()

    assert "data" in changed
    assert archived == [("Alex", teams["Alpha"]), ("Ben", teams["Bravo"])]
    assert clashing == {
        "detail": (
            "Ben can't play for both Alpha and Bravo in First cup. A player can be an active "
            "member of only one of a tournament's teams."
        )
    }
    assert reopened == {"success": True}
    assert followed == [("Ben", teams["Bravo"])]
