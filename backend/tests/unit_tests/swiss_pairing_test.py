import random
from decimal import Decimal

from bracket.logic.scheduling.swiss import get_swiss_pairing
from bracket.models.db.match import Match, MatchWithDetailsDefinitive
from bracket.models.db.stage_item import StageType
from bracket.models.db.stage_item_inputs import StageItemInput, StageItemInputFinal
from bracket.models.db.team import Team
from bracket.models.db.util import RoundWithMatches, StageItemWithRounds
from bracket.utils.dummy_records import DUMMY_MATCH1, DUMMY_MOCK_TIME, DUMMY_TEAM1
from bracket.utils.id_types import (
    MatchId,
    RoundId,
    StageId,
    StageItemId,
    StageItemInputId,
    TeamId,
    TournamentId,
)


def get_team(team_id: int, points: int = 1200, active: bool = True) -> StageItemInputFinal:
    return StageItemInputFinal(
        id=StageItemInputId(team_id),
        slot=team_id,
        tournament_id=TournamentId(-1),
        team_id=TeamId(team_id),
        points=Decimal(points),
        team=Team(**DUMMY_TEAM1.model_dump(), id=TeamId(team_id)).model_copy(
            update={"active": active}
        ),
    )


def get_round(*pairs: tuple[StageItemInputFinal, StageItemInputFinal]) -> RoundWithMatches:
    return RoundWithMatches(
        id=RoundId(-1),
        stage_item_id=StageItemId(-1),
        created=DUMMY_MOCK_TIME,
        is_draft=False,
        name="",
        matches=[
            MatchWithDetailsDefinitive(
                **Match.model_validate(
                    DUMMY_MATCH1.model_dump()
                    | {
                        "id": MatchId(-index),
                        "stage_item_input1_id": team1.id,
                        "stage_item_input2_id": team2.id,
                    }
                ).model_dump(),
                stage_item_input1=team1,
                stage_item_input2=team2,
            )
            for index, (team1, team2) in enumerate(pairs, start=1)
        ],
    )


def get_stage_item(
    teams: list[StageItemInputFinal], rounds: list[RoundWithMatches]
) -> StageItemWithRounds:
    return StageItemWithRounds(
        id=StageItemId(-1),
        stage_id=StageId(-1),
        name="Swiss",
        created=DUMMY_MOCK_TIME,
        type=StageType.SWISS,
        type_name="Swiss",
        team_count=len(teams),
        ranking_id=None,
        inputs=list[StageItemInput](teams),
        rounds=rounds,
    )


def pair_ids(stage_item: StageItemWithRounds) -> set[frozenset[int]]:
    pairing = get_swiss_pairing(stage_item, random.Random(0))
    return {frozenset((team1.id, team2.id)) for team1, team2 in pairing.pairs}


def test_pairs_teams_closest_in_standings() -> None:
    teams = [get_team(1, 1300), get_team(2, 1210), get_team(3, 1290), get_team(4, 1200)]

    assert pair_ids(get_stage_item(teams, [])) == {frozenset((1, 3)), frozenset((2, 4))}


def test_never_pairs_teams_that_already_played() -> None:
    team1, team2, team3, team4 = (get_team(team_id) for team_id in range(1, 5))
    rounds = [get_round((team1, team2), (team3, team4)), get_round((team1, team3), (team2, team4))]

    assert pair_ids(get_stage_item([team1, team2, team3, team4], rounds)) == {
        frozenset((1, 4)),
        frozenset((2, 3)),
    }


def test_pairs_every_team_when_greedy_pairing_would_strand_some() -> None:
    # After these rounds each team has two opponents left, forming the cycle 1-2-3-4-5-6-1.
    # Pairing top down with the closest opponent (1 vs 2, then 4 vs 5) would leave 3 and 6, who
    # already played each other.
    team1, team2, team3, team4, team5, team6 = (
        get_team(1, 1300),
        get_team(2, 1290),
        get_team(3, 1150),
        get_team(4, 1250),
        get_team(5, 1245),
        get_team(6, 1100),
    )
    rounds = [
        get_round((team1, team4), (team3, team5), (team2, team6)),
        get_round((team2, team5), (team1, team3), (team4, team6)),
        get_round((team3, team6), (team1, team5), (team2, team4)),
    ]
    stage_item = get_stage_item([team1, team2, team3, team4, team5, team6], rounds)

    assert pair_ids(stage_item) == {frozenset((1, 2)), frozenset((3, 4)), frozenset((5, 6))}


def test_lowest_ranked_team_that_has_not_sat_out_sits_out() -> None:
    team1, team2, team3, team4, team5 = (
        get_team(1, 1300),
        get_team(2, 1250),
        get_team(3, 1200),
        get_team(4, 1150),
        get_team(5, 1100),
    )
    # Team 5 sat out the first round, so team 4 is next in line.
    rounds = [get_round((team1, team2), (team3, team4))]
    pairing = get_swiss_pairing(
        get_stage_item([team1, team2, team3, team4, team5], rounds), random.Random(0)
    )

    assert [team.id for team in pairing.unpaired] == [4]
    assert len(pairing.pairs) == 2


def test_inactive_teams_are_not_paired() -> None:
    teams = [get_team(1), get_team(2), get_team(3, active=False)]
    pairing = get_swiss_pairing(get_stage_item(teams, []), random.Random(0))

    assert [(team1.id, team2.id) for team1, team2 in pairing.pairs] in ([(1, 2)], [(2, 1)])
    assert pairing.unpaired == []


def test_nothing_to_pair_when_every_team_has_played_every_other() -> None:
    team1, team2, team3 = (get_team(team_id) for team_id in range(1, 4))
    rounds = [get_round((team1, team2)), get_round((team1, team3)), get_round((team2, team3))]
    pairing = get_swiss_pairing(get_stage_item([team1, team2, team3], rounds), random.Random(0))

    assert pairing.pairs == []
    assert len(pairing.unpaired) == 3
