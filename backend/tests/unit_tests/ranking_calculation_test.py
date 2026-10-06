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

    assert ranking == {
        -2: TeamStatistics(
            wins=0, draws=1, losses=1, points=Decimal("1208"), score_for=2, score_against=4
        ),
        -1: TeamStatistics(
            wins=1, draws=1, losses=0, points=Decimal("1320"), score_for=4, score_against=2
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
    assert [input_id for input_id, _ in ranking] == [1, 3, 2, 4, 5]


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
    assert [input_id for input_id, _ in ranking] == [3, 2, 1]


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
