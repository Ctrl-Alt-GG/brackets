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
        # Teams and players outlive the tournament, so the flow deletes the ones it created.
        self.team_ids: set[int] = set()
        self.player_ids: set[int] = set()

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

    async def call_shared(
        self, method: HTTPMethod, endpoint: str, json: JsonDict | None = None
    ) -> JsonDict:
        """A request about the teams and players that every tournament shares."""
        return await send_auth_request(method, endpoint, self.auth_context, json=json)

    async def conflicts(self) -> list[JsonDict]:
        return list((await self.call(HTTPMethod.GET, "workspace"))["data"]["conflicts"])

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

    async def teams(self) -> list[JsonDict]:
        return list((await self.call(HTTPMethod.GET, "teams?limit=500"))["data"]["teams"])

    async def all_player_ids(self) -> set[int]:
        return {
            player["id"] for player in (await self.call_shared(HTTPMethod.GET, "players"))["data"]
        }

    async def add_teams(self, *lines: str) -> dict[str, int]:
        """
        Create teams that take part, from lines as organizers type them: a team's name, then its
        players. Returns every team of the tournament by name.
        """
        teams_before = {team["id"] for team in await self.teams()}
        players_before = await self.all_player_ids()
        response = await self.call(HTTPMethod.POST, "teams_multi", {"names": "\n".join(lines)})
        assert response == {"success": True}, response
        teams = await self.teams()
        self.team_ids.update({team["id"] for team in teams} - teams_before)
        self.player_ids.update(await self.all_player_ids() - players_before)
        return {team["name"]: team["id"] for team in teams}

    async def join(self, *team_ids: int) -> None:
        """Let teams that already exist, such as another tournament's, take part as well."""
        response = await self.call(HTTPMethod.POST, "teams", {"team_ids": list(team_ids)})
        assert response == {"success": True}, response

    async def delete_participants(self) -> None:
        """Delete the teams and players the flow created, once they take part nowhere."""
        for team_id in self.team_ids:
            deleted = await send_auth_request(
                HTTPMethod.DELETE, f"teams/{team_id}", self.auth_context
            )
            assert deleted == {"success": True}, deleted
        for player_id in self.player_ids:
            await send_auth_request(HTTPMethod.DELETE, f"players/{player_id}", self.auth_context)

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
            "start_time": "2030-06-01T10:00:00Z",
            "dashboard_public": False,
            "dashboard_endpoint": None,
            "duration_minutes": 30,
            "margin_minutes": 5,
        },
    )
    flow = TournamentFlow(auth_context, response["data"])
    try:
        yield flow
    finally:
        deleted = await send_auth_request(HTTPMethod.DELETE, f"tournaments/{flow.id}", auth_context)
        assert deleted == {"success": True}, deleted
        await flow.delete_participants()
