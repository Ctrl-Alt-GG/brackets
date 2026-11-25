from heliclockter import timedelta

from bracket.logic.planning.calendar import Booking, Calendar, Lineups
from bracket.logic.planning.matches import plan_match_timings
from bracket.models.db.match import (
    MatchTiming,
    MatchWithDetails,
    MatchWithDetailsDefinitive,
    MatchWithSlots,
)
from bracket.models.db.stage_item_inputs import StageItemInputFinal
from bracket.models.db.stage_tree import RoundWithMatches, StageItemWithRounds, StageWithStageItems
from bracket.models.db.tournament import Tournament
from bracket.models.enums import StageType
from bracket.utils.id_types import (
    MatchId,
    PlayerId,
    RankingId,
    RoundId,
    StageId,
    StageItemId,
    StageItemInputId,
    TeamId,
    TournamentId,
)
from tests.dummy_records import DUMMY_MOCK_TIME, DUMMY_TEAM1, DUMMY_TOURNAMENT, tournament_team


def get_round(round_id: int, *matches: MatchWithSlots) -> RoundWithMatches:
    return RoundWithMatches(
        id=RoundId(round_id),
        stage_item_id=StageItemId(-1),
        created=DUMMY_MOCK_TIME,
        is_draft=False,
        name="",
        matches=list(matches),
    )


def get_match(match_id: int, custom_duration_minutes: int | None = None) -> MatchWithDetails:
    return MatchWithDetails(
        id=MatchId(match_id),
        created=DUMMY_MOCK_TIME,
        duration_minutes=0,
        margin_minutes=0,
        custom_duration_minutes=custom_duration_minutes,
        round_id=RoundId(-1),
        stage_item_input1_score=0,
        stage_item_input2_score=0,
    )


def get_stage(
    stage_id: int,
    *rounds_per_stage_item: list[RoundWithMatches],
    custom_duration_minutes: int | None = None,
) -> StageWithStageItems:
    return StageWithStageItems(
        id=StageId(stage_id),
        tournament_id=TournamentId(-1),
        name="",
        created=DUMMY_MOCK_TIME,
        is_active=False,
        custom_duration_minutes=custom_duration_minutes,
        stage_items=[
            StageItemWithRounds(
                id=StageItemId(index),
                stage_id=StageId(stage_id),
                name="",
                created=DUMMY_MOCK_TIME,
                type=StageType.ROUND_ROBIN,
                team_count=4,
                ranking_id=RankingId(-1),
                inputs=[],
                rounds=rounds,
            )
            for index, rounds in enumerate(rounds_per_stage_item)
        ],
    )


def test_plan_match_timings() -> None:
    tournament = Tournament(**DUMMY_TOURNAMENT.model_dump(), id=TournamentId(-1))
    start = tournament.start_time
    round_minutes = tournament.duration_minutes + tournament.margin_minutes
    stages = [
        get_stage(
            2,
            [get_round(6, get_match(7))],
        ),
        get_stage(
            1,
            [
                get_round(1, get_match(1), get_match(2)),
                get_round(2, get_match(3), get_match(4, custom_duration_minutes=20)),
            ],
            [
                get_round(3, get_match(5)),
                get_round(4),
                get_round(5, get_match(6)),
            ],
        ),
    ]

    timings = {
        timing.match_id: (timing.start_time, timing.duration_minutes, timing.margin_minutes)
        for timing in plan_match_timings(stages, tournament)
    }

    first_round_end = start + timedelta(minutes=round_minutes)
    # The second round lasts as long as its longest match.
    stage_end = first_round_end + timedelta(minutes=20 + tournament.margin_minutes)
    default_timing = (tournament.duration_minutes, tournament.margin_minutes)
    assert timings == {
        # Both stage items of the first stage start together, with rounds back to back.
        1: (start, *default_timing),
        2: (start, *default_timing),
        3: (first_round_end, *default_timing),
        4: (first_round_end, 20, tournament.margin_minutes),
        5: (start, *default_timing),
        # Empty rounds take no time.
        6: (first_round_end, *default_timing),
        # The next stage starts when the slowest stage item of the previous stage has finished.
        7: (stage_end, *default_timing),
    }


def test_plan_match_timings_with_custom_stage_duration() -> None:
    tournament = Tournament(**DUMMY_TOURNAMENT.model_dump(), id=TournamentId(-1))
    start = tournament.start_time
    margin_minutes = tournament.margin_minutes
    stages = [
        get_stage(
            1,
            [
                get_round(1, get_match(1), get_match(2, custom_duration_minutes=45)),
                get_round(2, get_match(3)),
            ],
            custom_duration_minutes=30,
        ),
        get_stage(
            2,
            [get_round(3, get_match(4))],
        ),
    ]

    timings = {
        timing.match_id: (timing.start_time, timing.duration_minutes, timing.margin_minutes)
        for timing in plan_match_timings(stages, tournament)
    }

    first_round_end = start + timedelta(minutes=45 + margin_minutes)
    stage_end = first_round_end + timedelta(minutes=30 + margin_minutes)
    assert timings == {
        # The stage overwrites the match duration of the tournament.
        1: (start, 30, margin_minutes),
        # The custom duration of a match takes precedence over that of its stage.
        2: (start, 45, margin_minutes),
        3: (first_round_end, 30, margin_minutes),
        # Other stages keep the match duration of the tournament.
        4: (stage_end, tournament.duration_minutes, margin_minutes),
    }


def slot(team_id: int) -> StageItemInputFinal:
    return StageItemInputFinal(
        id=StageItemInputId(team_id),
        slot=team_id,
        stage_item_id=StageItemId(-1),
        tournament_id=TournamentId(-1),
        team_id=TeamId(team_id),
        team=tournament_team(DUMMY_TEAM1, team_id),
    )


def versus(match_id: int, team1: int, team2: int) -> MatchWithDetailsDefinitive:
    return MatchWithDetailsDefinitive(
        id=MatchId(match_id),
        created=DUMMY_MOCK_TIME,
        duration_minutes=0,
        margin_minutes=0,
        round_id=RoundId(-1),
        stage_item_input1=slot(team1),
        stage_item_input1_id=StageItemInputId(team1),
        stage_item_input2=slot(team2),
        stage_item_input2_id=StageItemInputId(team2),
        stage_item_input1_score=0,
        stage_item_input2_score=0,
    )


def test_matches_wait_for_teams_and_players_who_play_elsewhere() -> None:
    """
    Team 2 plays in another tournament until 20 minutes in, so its first match waits. The next
    round starts once that match is over. Alex plays for team 3, and is busy elsewhere when the
    second round would start.
    """
    tournament = Tournament(**DUMMY_TOURNAMENT.model_dump(), id=TournamentId(-1))
    start = tournament.start_time
    round_minutes = tournament.duration_minutes + tournament.margin_minutes
    alex = PlayerId(-10)
    elsewhere = Calendar()
    elsewhere.book_team(
        TeamId(2),
        Booking(MatchId(-100), TournamentId(-2), "Other", start, start + timedelta(minutes=20)),
    )
    second_round = start + timedelta(minutes=20 + round_minutes)
    elsewhere.book_player(
        alex,
        Booking(
            MatchId(-101),
            TournamentId(-2),
            "Other",
            second_round,
            second_round + timedelta(minutes=25),
        ),
    )
    stages = [
        get_stage(
            1,
            [
                get_round(1, versus(1, 1, 2), versus(2, 3, 4)),
                get_round(2, versus(3, 1, 3)),
            ],
        )
    ]

    timings = plan_match_timings(
        stages,
        tournament,
        lineups=Lineups({TeamId(3): frozenset({alex})}),
        elsewhere=elsewhere,
    )

    def timing(match_id: int, minutes: int) -> MatchTiming:
        return MatchTiming(
            match_id=MatchId(match_id),
            start_time=start + timedelta(minutes=minutes),
            duration_minutes=tournament.duration_minutes,
            margin_minutes=tournament.margin_minutes,
        )

    assert timings == [timing(1, 20), timing(2, 0), timing(3, 20 + round_minutes + 25)]
