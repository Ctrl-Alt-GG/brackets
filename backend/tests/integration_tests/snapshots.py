"""Normalize unstable snapshot values while retaining entity and foreign-key identity."""

from decimal import Decimal
from typing import Any

DECIMAL_FIELDS = {"points", "elo_score", "swiss_score", "win_points", "draw_points", "loss_points"}
REFERENCE_TYPES = {
    "club_id": "club",
    "tournament_id": "tournament",
    "stage_id": "stage",
    "stage_item_id": "item",
    "winner_from_stage_item_id": "item",
    "ranking_id": "ranking",
    "team_id": "team",
    "round_id": "round",
    "stage_item_input_id": "slot",
    "stage_item_input1_id": "slot",
    "stage_item_input2_id": "slot",
    "stage_item_input1_winner_from_match_id": "match",
    "stage_item_input2_winner_from_match_id": "match",
}


def entity_type(record: dict[str, Any]) -> str:
    if "stage_items" in record:
        return "stage"
    if "rounds" in record:
        return "item"
    if "matches" in record:
        return "round"
    if "round_id" in record:
        return "match"
    if "slot" in record:
        return "slot"
    if "win_points" in record:
        return "ranking"
    if "club_id" in record:
        return "tournament"
    if "players" in record or "logo_path" in record:
        return "team"
    if "active" in record:
        return "player"
    raise AssertionError(f"Unrecognized entity fields: {sorted(record)}")


def canonical_tournament(value: dict[str, Any], *, club_id: int) -> dict[str, Any]:
    identifiers: dict[tuple[str, int], str] = {("club", club_id): "event"}
    tournaments = value["tournaments?filter_=ALL"]["data"]
    for tournament in tournaments:
        identifiers["tournament", tournament["id"]] = f"tournament:{tournament['name']}"
    for team in value["teams"]["data"]["teams"]:
        identifiers["team", team["id"]] = f"team:{team['name']}"
    for player in value["players"]["data"]["players"]:
        identifiers["player", player["id"]] = f"player:{player['name']}"
    for ranking in value["rankings"]["data"]:
        identifiers["ranking", ranking["id"]] = f"ranking:{ranking['position']}"
    for stage_index, stage in enumerate(value["stages?no_draft_rounds=false"]["data"]):
        stage_label = f"stage:{stage_index}"
        identifiers["stage", stage["id"]] = stage_label
        for item in stage["stage_items"]:
            item_label = f"{stage_label}/item:{item['name']}"
            identifiers["item", item["id"]] = item_label
            for slot in item["inputs"]:
                identifiers["slot", slot["id"]] = f"{item_label}/slot:{slot['slot']}"
            for round_index, round_ in enumerate(item["rounds"]):
                round_label = f"{item_label}/round:{round_index}"
                identifiers["round", round_["id"]] = round_label
                for match_index, match in enumerate(round_["matches"]):
                    identifiers["match", match["id"]] = f"{round_label}/match:{match_index}"

    def normalize(item: Any, key: str = "", kind: str | None = None) -> Any:
        if key == "created":
            return "<created>"
        reference_type = kind if key == "id" else REFERENCE_TYPES.get(key)
        if reference_type is not None:
            return identifiers[reference_type, item] if item is not None else None
        if key in DECIMAL_FIELDS and isinstance(item, str):
            return format(Decimal(item).normalize(), "f")
        if isinstance(item, list):
            return [normalize(child) for child in item]
        if isinstance(item, dict):
            record_kind = entity_type(item) if "id" in item else None
            return {
                identifiers["item", int(name)] if name.lstrip("-").isdigit() else name: normalize(
                    child, name, record_kind
                )
                for name, child in item.items()
            }
        return item

    result: dict[str, Any] = normalize(value)
    return result
