"""
Runs a tournament through the API the way an organizer does: teams, stages, slots and results.

The other tests insert rows directly, which checks one endpoint at a time. The behaviour that
matters most to an organizer spans several of them, such as what a result does to the next stage.
"""

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from datetime import datetime
from http import HTTPMethod
from typing import Any

from bracket.utils.types import JsonDict
from tests.integration_tests.api.shared import send_auth_request, send_request
from tests.integration_tests.models import AuthContext


def parse_time(value: str) -> datetime:
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


class TournamentFlow:
    def __init__(self, auth_context: AuthContext, tournament: JsonDict) -> None:
        self.auth_context = auth_context
        self.id: int = tournament["id"]

    async def call(
        self,
        method: HTTPMethod,
        endpoint: str = "",
        json: JsonDict | None = None,
        *,
        anonymous: bool = False,
    ) -> JsonDict:
        path = f"tournaments/{self.id}/{endpoint}" if endpoint else f"tournaments/{self.id}"
        if anonymous:
            return await send_request(method, path, json=json)
        return await send_auth_request(method, path, self.auth_context, json=json)

    async def tournament(self) -> JsonDict:
        return JsonDict((await self.call(HTTPMethod.GET))["data"])

    async def stages(self) -> list[JsonDict]:
        return list((await self.call(HTTPMethod.GET, "stages"))["data"])

    async def stage_item(self, stage_item_id: int) -> JsonDict:
        return next(
            stage_item
            for stage in await self.stages()
            for stage_item in stage["stage_items"]
            if stage_item["id"] == stage_item_id
        )

    async def matches(self, stage_item_id: int) -> list[list[JsonDict]]:
        """The matches of a stage item, per round."""
        return [round_["matches"] for round_ in (await self.stage_item(stage_item_id))["rounds"]]

    async def add_teams(self, *names: str) -> dict[str, int]:
        await self.call(HTTPMethod.POST, "teams_multi", {"names": "\n".join(names), "active": True})
        teams = (await self.call(HTTPMethod.GET, "teams?limit=500"))["data"]["teams"]
        return {team["name"]: team["id"] for team in teams}

    async def add_stage(self) -> int:
        await self.call(HTTPMethod.POST, "stages")
        return int((await self.stages())[-1]["id"])

    async def add_stage_item(self, stage_id: int, type_: str, team_count: int, name: str) -> int:
        response = await self.call(
            HTTPMethod.POST,
            "stage_items",
            {
                "stage_id": stage_id,
                "name": name,
                "type": type_,
                "team_count": team_count,
                "ranking_id": None,
            },
        )
        assert response == {"success": True}, response
        stage = next(stage for stage in await self.stages() if stage["id"] == stage_id)
        return int(next(item for item in stage["stage_items"] if item["name"] == name)["id"])

    async def set_slot(self, stage_item_id: int, slot: int, body: JsonDict) -> JsonDict:
        """`slot` counts from 1, as organizers see it."""
        stage_item = await self.stage_item(stage_item_id)
        input_id = stage_item["inputs"][slot - 1]["id"]
        return await self.call(
            HTTPMethod.PUT, f"stage_items/{stage_item_id}/inputs/{input_id}", body
        )

    async def fill(self, stage_item_id: int, *team_ids: int) -> None:
        for slot, team_id in enumerate(team_ids, start=1):
            await self.set_slot(stage_item_id, slot, {"team_id": team_id})

    async def feed(self, stage_item_id: int, source_stage_item_id: int, *positions: int) -> None:
        for slot, position in enumerate(positions, start=1):
            await self.set_slot(
                stage_item_id,
                slot,
                {"winner_from_stage_item_id": source_stage_item_id, "winner_position": position},
            )

    async def score(self, match: JsonDict, score1: int, score2: int, **extra: Any) -> JsonDict:
        return await self.call(
            HTTPMethod.PUT,
            f"matches/{match['id']}",
            {"stage_item_input1_score": score1, "stage_item_input2_score": score2, **extra},
        )

    async def activate(self, direction: str = "next", **extra: Any) -> JsonDict:
        return await self.call(
            HTTPMethod.POST, "stages/activate", {"direction": direction, **extra}
        )


def names(match: JsonDict) -> tuple[str | None, str | None]:
    """Who plays a match, by team name. `None` for a slot that is undecided."""
    return (
        ((match["stage_item_input1"] or {}).get("team") or {}).get("name"),
        ((match["stage_item_input2"] or {}).get("team") or {}).get("name"),
    )


def result(match: JsonDict) -> tuple[int, int]:
    return match["stage_item_input1_score"], match["stage_item_input2_score"]


@asynccontextmanager
async def api_tournament(
    auth_context: AuthContext, name: str = "Flow tournament"
) -> AsyncIterator[TournamentFlow]:
    response = await send_auth_request(
        HTTPMethod.POST,
        "tournaments",
        auth_context,
        json={
            "name": name,
            "club_id": auth_context.club.id,
            "start_time": "2030-06-01T10:00:00Z",
            "dashboard_public": False,
            "dashboard_endpoint": None,
            "players_can_be_in_multiple_teams": False,
            "duration_minutes": 30,
            "margin_minutes": 5,
        },
    )
    flow = TournamentFlow(auth_context, response["data"])
    try:
        yield flow
    finally:
        await send_auth_request(HTTPMethod.DELETE, f"tournaments/{flow.id}", auth_context)
