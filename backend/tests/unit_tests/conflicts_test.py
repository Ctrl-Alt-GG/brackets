from datetime import timedelta

from bracket.logic.planning.conflicts import get_conflicting_matches
from bracket.models.db.util import StageWithStageItems
from bracket.utils.dummy_records import DUMMY_MOCK_TIME
from bracket.utils.id_types import StageId, StageItemInputId, TournamentId
from tests.integration_tests.mocks import MOCK_NOW
from tests.unit_tests.mocks import (
    get_2_definitive_matches_mock,
    get_one_round_with_two_definitive_matches,
    get_stage_item_inputs_mock,
    get_stage_item_mock,
)


def test_get_conflicting_matches_conflicts_to_set() -> None:
    """
    Test `get_conflicting_matches` returns the right conflicts to set
    """
    tournament_id = TournamentId(-1)
    stage_item_inputs = get_stage_item_inputs_mock(tournament_id)
    match1, match2 = get_2_definitive_matches_mock(stage_item_inputs)
    rounds = get_one_round_with_two_definitive_matches(match1, match2)
    stage_item = StageWithStageItems(
        id=StageId(-1),
        tournament_id=tournament_id,
        name="",
        created=MOCK_NOW,
        is_active=False,
        stage_items=[get_stage_item_mock(stage_item_inputs, [rounds])],
    )

    assert get_conflicting_matches([stage_item]) == ({-1: [True, False], -2: [True, False]}, set())


def test_get_conflicting_matches_conflicts_to_clear() -> None:
    """
    Test `get_conflicting_matches` returns the right conflicts to clear
    """
    tournament_id = TournamentId(-1)
    stage_item_inputs = get_stage_item_inputs_mock(tournament_id)
    # The matches take 105 minutes with their break, so two hours apart they don't touch.
    match1, match2 = get_2_definitive_matches_mock(
        stage_item_inputs, DUMMY_MOCK_TIME + timedelta(hours=2)
    )
    rounds = get_one_round_with_two_definitive_matches(match1, match2)
    stage_item = StageWithStageItems(
        id=StageId(-1),
        tournament_id=tournament_id,
        name="",
        created=MOCK_NOW,
        is_active=False,
        stage_items=[get_stage_item_mock(stage_item_inputs, [rounds])],
    )

    assert get_conflicting_matches([stage_item]) == ({}, {-1, -2})


def test_get_conflicting_matches_partial_overlap() -> None:
    """
    A match that starts while another one with the same team is still on conflicts with it, also
    when neither starts nor ends at the same moment as the other.
    """
    tournament_id = TournamentId(-1)
    stage_item_inputs = get_stage_item_inputs_mock(tournament_id)
    match1, match2 = get_2_definitive_matches_mock(
        stage_item_inputs, DUMMY_MOCK_TIME + timedelta(hours=1)
    )
    rounds = get_one_round_with_two_definitive_matches(match1, match2)
    stage_item = StageWithStageItems(
        id=StageId(-1),
        tournament_id=tournament_id,
        name="",
        created=MOCK_NOW,
        is_active=False,
        stage_items=[get_stage_item_mock(stage_item_inputs, [rounds])],
    )

    assert get_conflicting_matches([stage_item]) == ({-1: [True, False], -2: [True, False]}, set())


def test_conflicts_follow_teams_across_different_slots() -> None:
    tournament_id = TournamentId(-1)
    inputs = get_stage_item_inputs_mock(tournament_id)
    # The same team occupies two distinct slots, as it does in separate stage items.
    inputs[2] = inputs[2].model_copy(update={"id": StageItemInputId(-30)})
    match1, match2 = get_2_definitive_matches_mock(inputs)
    stage = StageWithStageItems(
        id=StageId(-1),
        tournament_id=tournament_id,
        name="",
        created=MOCK_NOW,
        is_active=False,
        stage_items=[
            get_stage_item_mock(inputs, [get_one_round_with_two_definitive_matches(match1, match2)])
        ],
    )

    assert get_conflicting_matches([stage]) == ({-1: [True, False], -2: [True, False]}, set())
