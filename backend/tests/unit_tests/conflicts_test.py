import random
from datetime import timedelta

import pytest

from bracket.logic.planning.conflicts import (
    get_conflicting_matches,
    matches_overlap,
    overlapping_matches,
)
from bracket.models.db.match import Match
from bracket.models.db.stage_tree import StageWithStageItems
from bracket.utils.id_types import MatchId, RoundId, StageId, StageItemInputId, TournamentId
from tests.dummy_records import DUMMY_MOCK_TIME
from tests.integration_tests.mocks import MOCK_NOW
from tests.unit_tests.mocks import (
    get_2_definitive_matches_mock,
    get_one_round_with_two_definitive_matches,
    get_stage_item_inputs_mock,
    get_stage_item_mock,
)


def test_get_conflicting_matches_simultaneous() -> None:
    """Two simultaneous matches of the same team conflict, for that team only."""
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

    assert get_conflicting_matches([stage_item]) == {-1: (True, False), -2: (True, False)}


def test_get_conflicting_matches_apart() -> None:
    """Matches of the same team that don't overlap don't conflict."""
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

    assert get_conflicting_matches([stage_item]) == {-1: (False, False), -2: (False, False)}


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

    assert get_conflicting_matches([stage_item]) == {-1: (True, False), -2: (True, False)}


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

    assert get_conflicting_matches([stage]) == {-1: (True, False), -2: (True, False)}


def timed_match(match_id: int, rng: random.Random) -> Match:
    return Match(
        id=MatchId(match_id),
        created=DUMMY_MOCK_TIME,
        # Some matches aren't planned yet, and many start or end on the same minute.
        start_time=(
            None
            if rng.random() < 0.1
            else DUMMY_MOCK_TIME + timedelta(minutes=rng.randrange(0, 180, 5))
        ),
        duration_minutes=rng.choice((5, 10, 15, 30)),
        margin_minutes=rng.choice((0, 5)),
        round_id=RoundId(1),
        stage_item_input1_score=0,
        stage_item_input2_score=0,
        stage_item_input1_conflict=False,
        stage_item_input2_conflict=False,
    )


@pytest.mark.parametrize("seed", range(50))
def test_the_sweep_finds_the_matches_that_overlap_another(seed: int) -> None:
    rng = random.Random(seed)
    matches = [timed_match(match_id, rng) for match_id in range(rng.randrange(0, 15))]
    expected = {
        match.id
        for match in matches
        if any(other is not match and matches_overlap(match, other) for other in matches)
    }
    assert overlapping_matches(matches) == expected


def test_matches_that_touch_do_not_overlap() -> None:
    first = timed_match(1, random.Random(0)).model_copy(
        update={"start_time": DUMMY_MOCK_TIME, "duration_minutes": 10, "margin_minutes": 5}
    )
    second = first.model_copy(
        update={"id": MatchId(2), "start_time": DUMMY_MOCK_TIME + timedelta(minutes=15)}
    )
    assert overlapping_matches([first, second]) == set()
    assert overlapping_matches(
        [first, second.model_copy(update={"start_time": DUMMY_MOCK_TIME + timedelta(minutes=14)})]
    ) == {1, 2}
