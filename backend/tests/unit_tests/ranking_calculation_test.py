from collections.abc import Sequence
from decimal import Decimal

from heliclockter import datetime_utc

from bracket.logic.ranking.calculation import (
    determine_ranking_for_stage_item,
    determine_team_ranking_for_stage_item,
)
from bracket.logic.ranking.statistics import TeamStatistics
from bracket.models.db.match import MatchWithDetails, MatchWithDetailsDefinitive
from bracket.models.db.ranking import Ranking
from bracket.models.db.stage_item import StageType
from bracket.models.db.stage_item_inputs import StageItemInputFinal
from bracket.models.db.team import Team
from bracket.models.db.util import RoundWithMatches, StageItemWithRounds
from bracket.utils.dummy_records import DUMMY_TEAM1, DUMMY_TEAM2
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


def test_determine_ranking_for_stage_item_elimination() -> None:
    tournament_id = TournamentId(-1)
    now = datetime_utc.now()
    stage_item_input1 = StageItemInputFinal(
        id=StageItemInputId(-1),
        team_id=TeamId(-1),
        slot=1,
        tournament_id=tournament_id,
        team=Team(**DUMMY_TEAM1.model_dump(), id=TeamId(-1)),
    )
    stage_item_input2 = StageItemInputFinal(
        id=StageItemInputId(-2),
        team_id=TeamId(-2),
        slot=1,
        tournament_id=tournament_id,
        team=Team(**DUMMY_TEAM2.model_dump(), id=TeamId(-2)),
    )

    ranking = determine_ranking_for_stage_item(
        StageItemWithRounds(
            rounds=[
                RoundWithMatches(
                    id=RoundId(-1),
                    matches=[
                        MatchWithDetailsDefinitive(
                            id=MatchId(-1),
                            stage_item_input1=stage_item_input1,
                            stage_item_input2=stage_item_input2,
                            created=now,
                            duration_minutes=90,
                            margin_minutes=15,
                            round_id=RoundId(-1),
                            stage_item_input1_score=2,
                            stage_item_input2_score=0,
                            stage_item_input1_conflict=False,
                            stage_item_input2_conflict=False,
                        ),
                        MatchWithDetailsDefinitive(
                            id=MatchId(-2),
                            stage_item_input1=stage_item_input1,
                            stage_item_input2=stage_item_input2,
                            created=now,
                            duration_minutes=90,
                            margin_minutes=15,
                            round_id=RoundId(-1),
                            stage_item_input1_score=2,
                            stage_item_input2_score=2,
                            stage_item_input1_conflict=False,
                            stage_item_input2_conflict=False,
                        ),
                        MatchWithDetails(  # This gets ignored in ranking calculation
                            id=MatchId(-3),
                            created=now,
                            duration_minutes=90,
                            margin_minutes=15,
                            round_id=RoundId(-1),
                            stage_item_input1_score=3,
                            stage_item_input2_score=2,
                            stage_item_input1_conflict=False,
                            stage_item_input2_conflict=False,
                        ),
                    ],
                    stage_item_id=StageItemId(-1),
                    created=now,
                    is_draft=False,
                    name="",
                )
            ],
            inputs=[stage_item_input1, stage_item_input2],
            type_name="Single Elimination",
            team_count=4,
            ranking_id=None,
            id=StageItemId(-1),
            stage_id=StageId(-1),
            name="",
            created=now,
            type=StageType.SINGLE_ELIMINATION,
        ),
        Ranking(
            id=RankingId(-1),
            tournament_id=tournament_id,
            created=now,
            win_points=Decimal("3.5"),
            draw_points=Decimal("1.25"),
            loss_points=Decimal("0.0"),
            add_score_points=False,
            position=0,
        ),
    )

    assert ranking == {
        -2: TeamStatistics(
            wins=0, draws=1, losses=1, points=Decimal("1.25"), score_for=2, score_against=4
        ),
        -1: TeamStatistics(
            wins=1, draws=1, losses=0, points=Decimal("4.75"), score_for=4, score_against=2
        ),
    }


def test_determine_ranking_for_stage_item_swiss() -> None:
    tournament_id = TournamentId(-1)
    now = datetime_utc.now()
    stage_item_input1 = StageItemInputFinal(
        id=StageItemInputId(-1),
        team_id=TeamId(-1),
        slot=1,
        tournament_id=tournament_id,
        team=Team(**DUMMY_TEAM1.model_dump(), id=TeamId(-1)),
    )
    stage_item_input2 = StageItemInputFinal(
        id=StageItemInputId(-2),
        team_id=TeamId(-2),
        slot=1,
        tournament_id=tournament_id,
        team=Team(**DUMMY_TEAM2.model_dump(), id=TeamId(-2)),
    )

    ranking = determine_ranking_for_stage_item(
        StageItemWithRounds(
            rounds=[
                RoundWithMatches(
                    id=RoundId(-1),
                    matches=[
                        MatchWithDetailsDefinitive(
                            id=MatchId(-1),
                            stage_item_input1=stage_item_input1,
                            stage_item_input2=stage_item_input2,
                            created=now,
                            duration_minutes=90,
                            margin_minutes=15,
                            round_id=RoundId(-1),
                            stage_item_input1_score=2,
                            stage_item_input2_score=0,
                            stage_item_input1_conflict=False,
                            stage_item_input2_conflict=False,
                        ),
                        MatchWithDetailsDefinitive(
                            id=MatchId(-2),
                            stage_item_input1=stage_item_input1,
                            stage_item_input2=stage_item_input2,
                            created=now,
                            duration_minutes=90,
                            margin_minutes=15,
                            round_id=RoundId(-1),
                            stage_item_input1_score=2,
                            stage_item_input2_score=2,
                            stage_item_input1_conflict=False,
                            stage_item_input2_conflict=False,
                        ),
                        MatchWithDetails(  # This gets ignored in ranking calculation
                            id=MatchId(-3),
                            created=now,
                            duration_minutes=90,
                            margin_minutes=15,
                            round_id=RoundId(-1),
                            stage_item_input1_score=3,
                            stage_item_input2_score=2,
                            stage_item_input1_conflict=False,
                            stage_item_input2_conflict=False,
                        ),
                    ],
                    stage_item_id=StageItemId(-1),
                    created=now,
                    is_draft=False,
                    name="",
                )
            ],
            inputs=[stage_item_input1, stage_item_input2],
            type_name="Swiss",
            team_count=4,
            ranking_id=None,
            id=StageItemId(-1),
            stage_id=StageId(-1),
            name="",
            created=now,
            type=StageType.SWISS,
        ),
        Ranking(
            id=RankingId(-1),
            tournament_id=tournament_id,
            created=now,
            win_points=Decimal("3.5"),
            draw_points=Decimal("1.25"),
            loss_points=Decimal("0.0"),
            add_score_points=False,
            position=0,
        ),
    )

    # The ranking awards 3.5 for a win. A rating doesn't: it moves by the result on a scale of 0 to
    # 1, so what one team gains the other loses.
    assert ranking == {
        -2: TeamStatistics(
            wins=0, draws=1, losses=1, points=Decimal("1184"), score_for=2, score_against=4
        ),
        -1: TeamStatistics(
            wins=1, draws=1, losses=0, points=Decimal("1216"), score_for=4, score_against=2
        ),
    }


def test_determine_ranking_for_stage_item_swiss_no_matches() -> None:
    tournament_id = TournamentId(-1)
    now = datetime_utc.now()
    stage_item_input1 = StageItemInputFinal(
        id=StageItemInputId(-1),
        team_id=TeamId(-1),
        slot=1,
        tournament_id=tournament_id,
        team=Team(**DUMMY_TEAM1.model_dump(), id=TeamId(-1)),
    )
    stage_item_input2 = StageItemInputFinal(
        id=StageItemInputId(-2),
        team_id=TeamId(-2),
        slot=1,
        tournament_id=tournament_id,
        team=Team(**DUMMY_TEAM2.model_dump(), id=TeamId(-2)),
    )

    ranking = determine_ranking_for_stage_item(
        StageItemWithRounds(
            rounds=[
                RoundWithMatches(
                    id=RoundId(-1),
                    matches=[],
                    stage_item_id=StageItemId(-1),
                    created=now,
                    is_draft=False,
                    name="",
                )
            ],
            inputs=[stage_item_input1, stage_item_input2],
            type_name="Swiss",
            team_count=2,
            ranking_id=None,
            id=StageItemId(-1),
            stage_id=StageId(-1),
            name="",
            created=now,
            type=StageType.SWISS,
        ),
        Ranking(
            id=RankingId(-1),
            tournament_id=tournament_id,
            created=now,
            win_points=Decimal("3.5"),
            draw_points=Decimal("1.25"),
            loss_points=Decimal("0.0"),
            add_score_points=False,
            position=0,
        ),
    )

    assert ranking == {
        -2: TeamStatistics(wins=0, draws=0, losses=0, points=Decimal("1200")),
        -1: TeamStatistics(wins=0, draws=0, losses=0, points=Decimal("1200")),
    }


DEFAULT_RANKING = Ranking(
    id=RankingId(-1),
    tournament_id=TournamentId(-1),
    created=datetime_utc.now(),
    win_points=Decimal("1.0"),
    draw_points=Decimal("0.5"),
    loss_points=Decimal("0.0"),
    add_score_points=False,
    position=0,
)


def make_input(input_id: int, slot: int, points: Decimal = Decimal("0")) -> StageItemInputFinal:
    return StageItemInputFinal(
        id=StageItemInputId(input_id),
        team_id=TeamId(input_id),
        slot=slot,
        tournament_id=TournamentId(-1),
        team=Team(**DUMMY_TEAM1.model_dump(), id=TeamId(input_id)),
        points=points,
    )


def make_match(
    match_id: int,
    input1: StageItemInputFinal,
    input2: StageItemInputFinal,
    score1: int,
    score2: int,
) -> MatchWithDetailsDefinitive:
    return MatchWithDetailsDefinitive(
        id=MatchId(match_id),
        stage_item_input1=input1,
        stage_item_input2=input2,
        created=datetime_utc.now(),
        duration_minutes=90,
        margin_minutes=15,
        round_id=RoundId(1),
        stage_item_input1_score=score1,
        stage_item_input2_score=score2,
        stage_item_input1_conflict=False,
        stage_item_input2_conflict=False,
    )


def make_stage_item(
    type_: StageType,
    inputs: Sequence[StageItemInputFinal],
    rounds: Sequence[Sequence[MatchWithDetailsDefinitive]],
) -> StageItemWithRounds:
    now = datetime_utc.now()
    return StageItemWithRounds(
        rounds=[
            RoundWithMatches(
                id=RoundId(index + 1),
                matches=[*matches],
                stage_item_id=StageItemId(1),
                created=now,
                is_draft=False,
                name="",
            )
            for index, matches in enumerate(rounds)
        ],
        inputs=[*inputs],
        type_name="",
        team_count=len(inputs),
        ranking_id=None,
        id=StageItemId(1),
        stage_id=StageId(1),
        name="",
        created=now,
        type=type_,
    )


def test_determine_ranking_for_stage_item_ignores_unplayed_matches() -> None:
    team1, team2, team3 = make_input(1, 1), make_input(2, 2), make_input(3, 3)
    stage_item = make_stage_item(
        StageType.ROUND_ROBIN,
        [team1, team2, team3],
        # An unplayed match reads as 0-0, and must not count as a draw.
        [[make_match(1, team1, team2, 2, 1), make_match(2, team2, team3, 0, 0)]],
    )

    assert determine_ranking_for_stage_item(stage_item, DEFAULT_RANKING) == {
        1: TeamStatistics(wins=1, points=Decimal("1.0"), score_for=2, score_against=1),
        2: TeamStatistics(losses=1, points=Decimal("0.0"), score_for=1, score_against=2),
        3: TeamStatistics(),
    }


def test_determine_team_ranking_for_stage_item_breaks_ties() -> None:
    teams = [make_input(input_id, slot=input_id) for input_id in range(1, 6)]
    first, second, third, fourth, fifth = teams
    stage_item = make_stage_item(
        StageType.ROUND_ROBIN,
        teams,
        [
            [
                make_match(1, second, fifth, 1, 0),
                make_match(2, third, fifth, 2, 1),
                make_match(3, fourth, fifth, 1, 0),
                make_match(4, first, fifth, 3, 0),
            ]
        ],
    )

    ranking = determine_team_ranking_for_stage_item(stage_item, DEFAULT_RANKING)

    # The first four have a point each: the first has the best score difference, the third
    # scored more than the second and fourth, and those two are still level, so their slots
    # decide.
    assert [placing.stage_item_input_id for placing in ranking] == [1, 3, 2, 4, 5]


def test_determine_team_ranking_for_stage_item_prefers_wins_over_draws() -> None:
    drawer, winner, opponent = make_input(1, 1), make_input(2, 2), make_input(3, 3)
    stage_item = make_stage_item(
        StageType.ROUND_ROBIN,
        [drawer, winner, opponent],
        [
            [make_match(1, drawer, opponent, 1, 1), make_match(2, winner, opponent, 2, 1)],
            [make_match(3, drawer, opponent, 2, 2), make_match(4, opponent, winner, 2, 1)],
        ],
    )

    ranking = determine_team_ranking_for_stage_item(stage_item, DEFAULT_RANKING)

    # The drawer and the winner have the same points and scores, but the winner won a match.
    assert [placing.stage_item_input_id for placing in ranking] == [3, 2, 1]


def test_two_teams_level_on_points_are_ranked_by_their_match() -> None:
    first, second, third, fourth = (
        make_input(input_id, slot) for input_id, slot in ((1, 1), (2, 2), (3, 4), (4, 3))
    )
    stage_item = make_stage_item(
        StageType.ROUND_ROBIN,
        [first, second, third, fourth],
        [
            [make_match(1, second, first, 1, 0), make_match(2, third, fourth, 1, 0)],
            [make_match(3, first, third, 4, 0), make_match(4, second, fourth, 0, 1)],
            [make_match(5, first, fourth, 4, 0), make_match(6, second, third, 1, 0)],
        ],
    )

    ranking = determine_team_ranking_for_stage_item(stage_item, DEFAULT_RANKING)

    # The first two teams have two wins each, and the last two one each. The first team has the
    # better score difference and the earlier slot, but lost to the second. The fourth team has
    # the earlier slot of the last two, but lost to the third.
    assert [placing.stage_item_input_id for placing in ranking] == [2, 1, 3, 4]


def test_three_teams_level_on_points_are_ranked_by_their_matches() -> None:
    a, b, c, d, e = (
        make_input(input_id, slot) for input_id, slot in ((1, 3), (2, 2), (3, 1), (4, 4), (5, 5))
    )
    stage_item = make_stage_item(
        StageType.ROUND_ROBIN,
        [a, b, c, d, e],
        [
            [make_match(1, a, b, 1, 0), make_match(2, a, c, 1, 0), make_match(3, b, c, 1, 0)],
            [make_match(4, d, a, 1, 0), make_match(5, e, a, 1, 0), make_match(6, b, d, 5, 0)],
            [make_match(7, e, b, 1, 0), make_match(8, c, d, 9, 0), make_match(9, c, e, 9, 0)],
            [make_match(10, d, e, 1, 1)],
        ],
    )

    ranking = determine_team_ranking_for_stage_item(stage_item, DEFAULT_RANKING)

    # A, B and C have two points each. Against each other A won twice and B once, although C has
    # by far the best score difference overall and the earliest slot.
    assert [placing.stage_item_input_id for placing in ranking] == [5, 1, 2, 3, 4]
    level = [placing.tiebreak for placing in ranking[1:4]]
    assert level[0] < level[1] < level[2]


def test_teams_level_on_every_criterion_share_their_tiebreak() -> None:
    first, second, third = make_input(1, 1), make_input(2, 2), make_input(3, 3)
    stage_item = make_stage_item(
        StageType.ROUND_ROBIN,
        [first, second, third],
        [
            [make_match(1, first, second, 1, 1), make_match(2, first, third, 1, 1)],
            [make_match(3, second, third, 1, 1)],
        ],
    )

    ranking = determine_team_ranking_for_stage_item(stage_item, DEFAULT_RANKING)

    # Only their slots separate them, which activating the next stage warns about.
    assert [placing.stage_item_input_id for placing in ranking] == [1, 2, 3]
    assert len({placing.tiebreak for placing in ranking}) == 1


def test_determine_ranking_for_stage_item_swiss_replays_matches_in_order() -> None:
    # The points stored on the inputs are stale, and must not influence the ratings.
    team1, team2, team3 = (
        make_input(input_id, input_id, Decimal("1500")) for input_id in (1, 2, 3)
    )
    stage_item = make_stage_item(
        StageType.SWISS,
        [team1, team2, team3],
        [[make_match(1, team1, team2, 2, 0)], [make_match(2, team1, team3, 2, 0)]],
    )

    ranking = determine_ranking_for_stage_item(stage_item, DEFAULT_RANKING)

    # Both teams start at 1200, so the first win is worth 16 points. The second opponent is rated
    # lower than the 1216 of the first team by then, so that win is worth less.
    assert {input_id: statistics.points for input_id, statistics in ranking.items()} == {
        1: Decimal("1231"),
        2: Decimal("1184"),
        3: Decimal("1185"),
    }
