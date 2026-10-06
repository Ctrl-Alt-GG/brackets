from decimal import Decimal

from heliclockter import datetime_utc, timedelta

from bracket.logic.ranking.players import determine_player_statistics
from bracket.logic.ranking.statistics import PlayerStatistics
from bracket.models.db.match import MatchWithDetailsDefinitive
from bracket.models.db.player import Player
from bracket.models.db.stage_item import StageType
from bracket.models.db.stage_item_inputs import StageItemInputFinal
from bracket.models.db.team import FullTeamWithPlayers, Team
from bracket.models.db.util import RoundWithMatches, StageItemWithRounds, StageWithStageItems
from bracket.utils.dummy_records import DUMMY_MOCK_TIME, DUMMY_PLAYER1, DUMMY_TEAM1
from bracket.utils.id_types import (
    MatchId,
    PlayerId,
    RoundId,
    StageId,
    StageItemId,
    StageItemInputId,
    TeamId,
    TournamentId,
)


def make_team(team_id: int, player_ids: list[int]) -> FullTeamWithPlayers:
    return FullTeamWithPlayers(
        **DUMMY_TEAM1.model_dump(),
        id=TeamId(team_id),
        players=[
            Player(**DUMMY_PLAYER1.model_dump(), id=PlayerId(player_id)) for player_id in player_ids
        ],
    )


def make_input(team_id: int) -> StageItemInputFinal:
    return StageItemInputFinal(
        id=StageItemInputId(team_id),
        team_id=TeamId(team_id),
        slot=team_id,
        tournament_id=TournamentId(1),
        team=Team(**DUMMY_TEAM1.model_dump(), id=TeamId(team_id)),
    )


def make_round(
    round_id: int, matches: list[tuple[int, int, int, int]], is_draft: bool = False
) -> RoundWithMatches:
    """A round of `(team1, team2, score1, score2)` matches that start together."""
    start_time = DUMMY_MOCK_TIME + timedelta(hours=round_id)
    return RoundWithMatches(
        id=RoundId(round_id),
        matches=[
            MatchWithDetailsDefinitive(
                id=MatchId(round_id * 10 + index),
                stage_item_input1=make_input(team1),
                stage_item_input2=make_input(team2),
                created=DUMMY_MOCK_TIME,
                start_time=start_time,
                duration_minutes=10,
                margin_minutes=5,
                round_id=RoundId(round_id),
                stage_item_input1_score=score1,
                stage_item_input2_score=score2,
                stage_item_input1_conflict=False,
                stage_item_input2_conflict=False,
            )
            for index, (team1, team2, score1, score2) in enumerate(matches)
        ],
        stage_item_id=StageItemId(1),
        created=DUMMY_MOCK_TIME,
        is_draft=is_draft,
        name="",
    )


def make_stages(rounds: list[RoundWithMatches]) -> list[StageWithStageItems]:
    now = datetime_utc.now()
    return [
        StageWithStageItems(
            id=StageId(1),
            tournament_id=TournamentId(1),
            created=now,
            is_active=True,
            name="",
            stage_items=[
                StageItemWithRounds(
                    id=StageItemId(1),
                    stage_id=StageId(1),
                    name="",
                    created=now,
                    type=StageType.ROUND_ROBIN,
                    team_count=3,
                    ranking_id=None,
                    type_name="",
                    rounds=rounds,
                    inputs=[make_input(1), make_input(2), make_input(3)],
                )
            ],
        )
    ]


def test_determine_player_statistics() -> None:
    teams = [make_team(1, [1, 2]), make_team(2, [3]), make_team(3, [])]
    stages = make_stages(
        [
            # The unplayed 0-0 match and the draft round don't count.
            make_round(1, [(1, 2, 2, 0), (1, 3, 0, 0)]),
            make_round(2, [(2, 1, 1, 1)]),
            make_round(3, [(2, 1, 5, 0)], is_draft=True),
        ]
    )

    # Every rating starts at 1200, so the first win is worth 16 points. The second match is a draw
    # between teams rated 1216 and 1184, which costs the stronger team a little.
    assert determine_player_statistics(stages, teams) == {
        1: PlayerStatistics(
            wins=1, draws=1, losses=0, elo_score=Decimal("1215"), swiss_score=Decimal("1.5")
        ),
        2: PlayerStatistics(
            wins=1, draws=1, losses=0, elo_score=Decimal("1215"), swiss_score=Decimal("1.5")
        ),
        3: PlayerStatistics(
            wins=0, draws=1, losses=1, elo_score=Decimal("1185"), swiss_score=Decimal("0.5")
        ),
    }


def test_determine_player_statistics_replays_matches_in_schedule_order() -> None:
    teams = [make_team(1, [1]), make_team(2, [2]), make_team(3, [3])]
    later_round, earlier_round = make_round(1, [(1, 2, 1, 0)]), make_round(2, [(3, 1, 1, 0)])
    later_round = later_round.model_copy(
        update={
            "matches": [
                match.model_copy(update={"start_time": DUMMY_MOCK_TIME + timedelta(days=1)})
                for match in later_round.matches
            ]
        }
    )

    statistics = determine_player_statistics(make_stages([later_round, earlier_round]), teams)

    # Player 1 first loses to player 3 at 1200 each, and then beats player 2 while rated lower.
    assert {player_id: stats.elo_score for player_id, stats in statistics.items()} == {
        1: Decimal("1201"),
        2: Decimal("1183"),
        3: Decimal("1216"),
    }
