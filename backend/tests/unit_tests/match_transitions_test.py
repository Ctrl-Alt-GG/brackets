import pytest

from bracket.logic.ranking.elimination import get_inputs_to_update_in_subsequent_elimination_rounds
from bracket.models.db.match import MatchBody, MatchWithDetails, MatchWithDetailsDefinitive
from bracket.utils.id_types import RoundId, TournamentId
from tests.unit_tests.mocks import (
    get_2_definitive_and_2_tentative_matches_mock,
    get_one_round_with_two_definitive_matches,
    get_stage_item_inputs_mock,
    get_stage_item_mock,
    get_two_round_with_one_tentative_match_each,
)


@pytest.mark.parametrize(
    ("score1", "score2", "marker", "expected"),
    [(0, 0, False, False), (0, 0, True, True), (1, 0, True, False), (0, 2, True, False)],
)
def test_match_result_normalizes_the_scoreless_marker(
    score1: int, score2: int, marker: bool, expected: bool
) -> None:
    result = MatchBody(
        stage_item_input1_score=score1,
        stage_item_input2_score=score2,
        scoreless_result=marker,
        custom_duration_minutes=None,
        custom_margin_minutes=None,
    )
    assert result.scoreless_result is expected
    assert result.model_dump()["scoreless_result"] is expected


def test_knockout_updates_validate_both_match_variants() -> None:
    inputs = get_stage_item_inputs_mock(TournamentId(-1))
    first, second, final, later = get_2_definitive_and_2_tentative_matches_mock(inputs)
    rounds = [
        get_one_round_with_two_definitive_matches(first, second),
        *get_two_round_with_one_tentative_match_each(final, later),
    ]
    item = get_stage_item_mock(inputs, rounds)
    filled = get_inputs_to_update_in_subsequent_elimination_rounds(RoundId(-3), item)
    populated_final = filled[final.id]
    assert isinstance(populated_final, MatchWithDetailsDefinitive)
    assert populated_final.stage_item_input1_id == inputs[0].id
    assert populated_final.stage_item_input2_id == inputs[3].id
    assert (
        MatchWithDetailsDefinitive.model_validate(populated_final.model_dump()) == populated_final
    )

    item.rounds[1].matches = [populated_final]
    first.stage_item_input1_score = 0
    first.stage_item_input2_score = 0
    cleared = get_inputs_to_update_in_subsequent_elimination_rounds(RoundId(-3), item, {first.id})[
        final.id
    ]
    assert type(cleared) is MatchWithDetails
    assert cleared.stage_item_input1 is None
    assert cleared.stage_item_input2_id == inputs[3].id
    assert not cleared.played
    assert MatchWithDetails.model_validate(cleared.model_dump()) == cleared
