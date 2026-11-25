"""A match variant holds what its name promises, also when built from contradictory values."""

from typing import Any

import pytest
from pydantic import TypeAdapter, ValidationError

from bracket.models.db.match import (
    MatchWithDetails,
    MatchWithDetailsDefinitive,
    MatchWithSlots,
    with_slots,
)
from bracket.models.db.stage_item_inputs import StageItemInputEmpty
from bracket.utils.id_types import (
    MatchId,
    RoundId,
    StageItemId,
    StageItemInputId,
    TournamentId,
)
from tests.dummy_records import DUMMY_MOCK_TIME


def slot(id_: int) -> StageItemInputEmpty:
    return StageItemInputEmpty(
        id=StageItemInputId(id_),
        slot=id_,
        tournament_id=TournamentId(1),
        stage_item_id=StageItemId(1),
    )


def match_fields(**fields: Any) -> dict[str, Any]:
    return {
        "id": MatchId(1),
        "created": DUMMY_MOCK_TIME,
        "duration_minutes": 10,
        "margin_minutes": 5,
        "round_id": RoundId(1),
        "stage_item_input1_score": 0,
        "stage_item_input2_score": 0,
    } | fields


@pytest.mark.parametrize(
    "ids",
    [
        {},
        {"stage_item_input1_id": None, "stage_item_input2_id": None},
        {"stage_item_input1_id": 2, "stage_item_input2_id": 1},
        {"stage_item_input1_id": 1, "stage_item_input2_id": 3},
    ],
)
def test_a_definitive_match_needs_the_ids_of_its_slots(ids: dict[str, Any]) -> None:
    with pytest.raises(ValidationError):
        MatchWithDetailsDefinitive(
            **match_fields(stage_item_input1=slot(1), stage_item_input2=slot(2), **ids)
        )


@pytest.mark.parametrize(
    "fields",
    [
        # Both slots known: that is the definitive variant.
        {
            "stage_item_input1_id": 1,
            "stage_item_input2_id": 2,
            "stage_item_input1": slot(1),
            "stage_item_input2": slot(2),
        },
        # An id without its slot, or a slot without its id.
        {"stage_item_input1_id": 1},
        {"stage_item_input2": slot(2)},
    ],
)
def test_a_match_with_details_has_at_most_one_slot_that_agrees_with_its_id(
    fields: dict[str, Any],
) -> None:
    with pytest.raises(ValidationError):
        MatchWithDetails(**match_fields(**fields))


@pytest.mark.parametrize(
    ("fields", "variant"),
    [
        ({}, MatchWithDetails),
        ({"stage_item_input2_id": 2, "stage_item_input2": slot(2)}, MatchWithDetails),
        (
            {
                "stage_item_input1_id": 1,
                "stage_item_input2_id": 2,
                "stage_item_input1": slot(1),
                "stage_item_input2": slot(2),
            },
            MatchWithDetailsDefinitive,
        ),
    ],
)
def test_each_variant_survives_a_round_trip(fields: dict[str, Any], variant: type) -> None:
    adapter: TypeAdapter[MatchWithSlots] = TypeAdapter(MatchWithSlots)
    match = adapter.validate_python(match_fields(**fields))
    assert type(match) is variant
    assert adapter.validate_json(adapter.dump_json(match)) == match


def test_filling_and_clearing_a_slot_changes_the_variant() -> None:
    waiting = MatchWithDetails(**match_fields(stage_item_input1_id=1, stage_item_input1=slot(1)))

    filled = with_slots(waiting, slot(1), slot(2))
    assert type(filled) is MatchWithDetailsDefinitive
    assert filled.stage_item_input_ids == [1, 2]

    cleared = with_slots(filled, None, slot(2), stage_item_input2_score=0)
    assert type(cleared) is MatchWithDetails
    assert (cleared.stage_item_input1_id, cleared.stage_item_input2_id) == (None, 2)
