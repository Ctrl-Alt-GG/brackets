from copy import deepcopy
from typing import Any

from tests.integration_tests.snapshots import canonical_tournament


def snapshot() -> dict[str, Any]:
    return {
        "tournaments?filter_=ALL": {"data": [{"id": 1, "name": "Cup", "dashboard_endpoint": None}]},
        "teams": {
            "data": {
                "teams": [
                    {"id": 11, "name": "Alpha", "players": []},
                    {"id": 12, "name": "Bravo", "players": []},
                ]
            }
        },
        "players": {"data": {"players": []}},
        "rankings": {"data": [{"id": 21, "position": 0, "win_points": "1.0"}]},
        "stages?no_draft_rounds=false": {
            "data": [
                {
                    "id": 31,
                    "stage_items": [
                        {
                            "id": 41,
                            "name": "Final",
                            "inputs": [
                                {"id": 51, "slot": 1, "team_id": 11},
                                {"id": 52, "slot": 2, "team_id": 12},
                            ],
                            "rounds": [
                                {
                                    "id": 61,
                                    "matches": [
                                        {
                                            "id": 71,
                                            "round_id": 61,
                                            "stage_item_input1_id": 51,
                                            "stage_item_input1_winner_from_match_id": None,
                                        },
                                        {
                                            "id": 72,
                                            "round_id": 61,
                                            "stage_item_input1_id": 52,
                                            "stage_item_input1_winner_from_match_id": 71,
                                        },
                                    ],
                                }
                            ],
                        }
                    ],
                }
            ]
        },
        "standings": {"data": {"41": [{"stage_item_input_id": 51}]}},
    }


def test_snapshot_retains_team_and_winner_identity() -> None:
    original = snapshot()
    changed = deepcopy(original)
    item = changed["stages?no_draft_rounds=false"]["data"][0]["stage_items"][0]
    item["inputs"][0]["team_id"] = 12
    assert canonical_tournament(original) != canonical_tournament(changed)
    changed = deepcopy(original)
    item = changed["stages?no_draft_rounds=false"]["data"][0]["stage_items"][0]
    item["rounds"][0]["matches"][1]["stage_item_input1_winner_from_match_id"] = 72
    assert canonical_tournament(original) != canonical_tournament(changed)


def test_snapshot_preserves_json_types_but_ignores_decimal_scale() -> None:
    original = snapshot()
    changed = deepcopy(original)
    changed["rankings"]["data"][0]["win_points"] = "1.000000"
    assert canonical_tournament(original) == canonical_tournament(changed)
    changed["rankings"]["data"][0]["win_points"] = 1
    assert canonical_tournament(original) != canonical_tournament(changed)


def test_snapshot_retains_standings_keys() -> None:
    result = canonical_tournament(snapshot())
    assert list(result["standings"]["data"]) == ["stage:0/item:Final"]
    assert result["standings"]["data"]["stage:0/item:Final"] == [
        {"stage_item_input_id": "stage:0/item:Final/slot:1"}
    ]
