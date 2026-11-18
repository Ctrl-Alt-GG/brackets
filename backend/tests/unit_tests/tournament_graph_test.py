from typing import Any

import pytest

from bracket.logic.tournament_graph import TournamentGraph
from bracket.models.db.match import (
    MatchWithDetails,
    MatchWithDetailsDefinitive,
    with_slots,
)
from bracket.models.db.stage_item_inputs import StageItemInputEmpty, StageItemInputFinal
from bracket.models.db.stage_tree import RoundWithMatches, StageItemWithRounds, StageWithStageItems
from bracket.models.db.team import Team
from bracket.models.enums import StageType
from bracket.utils.id_types import (
    MatchId,
    RankingId,
    RoundId,
    StageId,
    StageItemId,
    StageItemInputId,
    TeamId,
    TournamentId,
)
from tests.dummy_records import DUMMY_MOCK_TIME, DUMMY_TEAM1

TOURNAMENT = TournamentId(1)


def team(id_: int, name: str) -> Team:
    return Team(
        **DUMMY_TEAM1.model_dump() | {"name": name, "tournament_id": TOURNAMENT}, id=TeamId(id_)
    )


def slot(id_: int, assigned: Team | None = None) -> StageItemInputFinal | StageItemInputEmpty:
    fields: dict[str, Any] = {
        "id": StageItemInputId(id_),
        "slot": id_,
        "tournament_id": TOURNAMENT,
        "stage_item_id": StageItemId(1),
    }
    if assigned is None:
        return StageItemInputEmpty(**fields)
    return StageItemInputFinal(**fields, team_id=assigned.id, team=assigned)


def graph() -> TournamentGraph:
    alpha, bravo, empty = slot(1, team(1, "Alpha")), slot(2, team(2, "Bravo")), slot(3)
    match_fields: dict[str, Any] = {
        "created": DUMMY_MOCK_TIME,
        "duration_minutes": 10,
        "margin_minutes": 5,
        "round_id": RoundId(1),
        "stage_item_input1_score": 0,
        "stage_item_input2_score": 0,
        "stage_item_input1_conflict": False,
        "stage_item_input2_conflict": False,
    }
    played = MatchWithDetailsDefinitive(
        id=MatchId(1),
        stage_item_input1=alpha,
        stage_item_input2=bravo,
        stage_item_input1_id=alpha.id,
        stage_item_input2_id=bravo.id,
        **match_fields,
    )
    waiting = MatchWithDetails(
        id=MatchId(2), stage_item_input1=empty, stage_item_input1_id=empty.id, **match_fields
    )
    stage_item = StageItemWithRounds(
        id=StageItemId(1),
        stage_id=StageId(1),
        name="Group",
        created=DUMMY_MOCK_TIME,
        type=StageType.ROUND_ROBIN,
        team_count=3,
        ranking_id=RankingId(1),
        inputs=[alpha, bravo, empty],
        rounds=[
            RoundWithMatches(
                id=RoundId(1),
                stage_item_id=StageItemId(1),
                created=DUMMY_MOCK_TIME,
                is_draft=False,
                name="Round 01",
                matches=[played, waiting],
            )
        ],
    )
    return TournamentGraph(
        [
            StageWithStageItems(
                id=StageId(1),
                tournament_id=TOURNAMENT,
                name="Groups",
                created=DUMMY_MOCK_TIME,
                is_active=True,
                stage_items=[stage_item],
            )
        ]
    )


def test_a_replaced_slot_replaces_every_copy() -> None:
    tree = graph()
    renamed = slot(1, team(1, "Alpha renamed"))
    tree.replace_slots({renamed.id: renamed})

    [stage_item] = tree.stage_items()
    assert stage_item.inputs[0] is renamed
    assert tree.match(MatchId(1)).stage_item_input1 is renamed
    assert tree.match(MatchId(1)).stage_item_input2 is stage_item.inputs[1]


def test_a_slot_can_only_replace_the_slot_with_its_id() -> None:
    tree = graph()
    with pytest.raises(ValueError, match="can't replace"):
        tree.replace_slots({StageItemInputId(2): slot(1, team(1, "Alpha"))})
    assert [input_.id for input_ in tree.stage_item(StageItemId(1)).inputs] == [1, 2, 3]


def test_slots_change_by_replacing_the_match() -> None:
    tree = graph()
    tree.update_match(MatchId(1), stage_item_input1_score=3, stage_item_input2_score=1)
    assert tree.match(MatchId(1)).played

    with pytest.raises(ValueError, match="replace_matches"):
        tree.update_match(MatchId(2), stage_item_input2_id=StageItemInputId(2))

    waiting = tree.match(MatchId(2))
    _, round_ = tree.locate_round(RoundId(1))
    filled = with_slots(
        waiting, waiting.stage_item_input1, tree.stage_item(StageItemId(1)).inputs[1]
    )
    tree.replace_matches({MatchId(2): filled})
    assert type(tree.match(MatchId(2))) is MatchWithDetailsDefinitive
    assert round_.matches[1] is filled

    with pytest.raises(ValueError, match="can't replace"):
        tree.replace_matches({MatchId(1): filled})
