from heliclockter import timedelta

from bracket.logic.planning.matches import plan_match_timings
from bracket.models.db.match import MatchWithDetails
from bracket.models.db.stage_item import StageType
from bracket.models.db.tournament import Tournament
from bracket.models.db.util import RoundWithMatches, StageItemWithRounds, StageWithStageItems
from bracket.utils.dummy_records import DUMMY_MOCK_TIME, DUMMY_TOURNAMENT
from bracket.utils.id_types import MatchId, RoundId, StageId, StageItemId, TournamentId


def get_round(round_id: int, *matches: MatchWithDetails) -> RoundWithMatches:
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
        stage_item_input1_conflict=False,
        stage_item_input2_conflict=False,
    )


def get_stage(stage_id: int, *rounds_per_stage_item: list[RoundWithMatches]) -> StageWithStageItems:
    return StageWithStageItems(
        id=StageId(stage_id),
        tournament_id=TournamentId(-1),
        name="",
        created=DUMMY_MOCK_TIME,
        is_active=False,
        stage_items=[
            StageItemWithRounds(
                id=StageItemId(index),
                stage_id=StageId(stage_id),
                name="",
                created=DUMMY_MOCK_TIME,
                type=StageType.ROUND_ROBIN,
                type_name="Round robin",
                team_count=4,
                ranking_id=None,
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
