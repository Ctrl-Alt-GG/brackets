import random
from datetime import timedelta

import pytest
from heliclockter import datetime_utc

from bracket.logic.planning.calendar import Booking, Calendar, Competitors, Lineups
from bracket.logic.planning.conflicts import find_conflicts
from bracket.models.db.stage_tree import StageWithStageItems
from bracket.models.db.tournament import Tournament
from bracket.models.schedule import ScheduleConflict
from bracket.utils.id_types import (
    MatchId,
    PlayerId,
    StageId,
    StageItemInputId,
    TeamId,
    TournamentId,
)
from tests.dummy_records import DUMMY_MOCK_TIME, DUMMY_TOURNAMENT
from tests.integration_tests.mocks import MOCK_NOW
from tests.unit_tests.mocks import (
    get_2_definitive_matches_mock,
    get_one_round_with_two_definitive_matches,
    get_stage_item_inputs_mock,
    get_stage_item_mock,
)

TOURNAMENT = Tournament(**DUMMY_TOURNAMENT.model_dump(), id=TournamentId(-1))
OTHER_TOURNAMENT = TournamentId(-2)
ALEX, BEA = PlayerId(-10), PlayerId(-11)


def at(minutes: int) -> datetime_utc:
    return DUMMY_MOCK_TIME + timedelta(minutes=minutes)


def booking(match_id: int, start: int, end: int) -> Booking:
    """A match of the other tournament, from `start` to `end` minutes into the day."""
    return Booking(MatchId(match_id), OTHER_TOURNAMENT, "Other cup", at(start), at(end))


def stage_with_two_matches(
    match1_start: datetime_utc = DUMMY_MOCK_TIME, *, distinct_slots: bool = False
) -> StageWithStageItems:
    """
    Two matches that take 105 minutes with their break: team -1 against -2 from `match1_start`,
    and team -1 against -4 from the start of the day. With `distinct_slots`, team -1 has a
    different slot in each, as it does in separate stage items.
    """
    inputs = get_stage_item_inputs_mock(TOURNAMENT.id)
    if distinct_slots:
        inputs[2] = inputs[2].model_copy(update={"id": StageItemInputId(-30)})
    match1, match2 = get_2_definitive_matches_mock(inputs, match1_start)
    return StageWithStageItems(
        id=StageId(-1),
        tournament_id=TOURNAMENT.id,
        name="",
        created=MOCK_NOW,
        is_active=False,
        stage_items=[
            get_stage_item_mock(inputs, [get_one_round_with_two_definitive_matches(match1, match2)])
        ],
    )


def conflict(
    match_id: int,
    team_id: int,
    other_match_id: int,
    *,
    players: list[PlayerId] | None = None,
    elsewhere: bool = False,
) -> ScheduleConflict:
    return ScheduleConflict(
        match_id=MatchId(match_id),
        team_id=TeamId(team_id),
        player_ids=players or [],
        other_match_id=MatchId(other_match_id),
        other_tournament_id=OTHER_TOURNAMENT if elsewhere else TOURNAMENT.id,
        other_tournament_name="Other cup" if elsewhere else TOURNAMENT.name,
    )


def test_a_team_in_two_simultaneous_matches_clashes_in_both() -> None:
    conflicts = find_conflicts(TOURNAMENT, [stage_with_two_matches()], Lineups({}), Calendar())
    assert conflicts == [conflict(-1, -1, -2), conflict(-2, -1, -1)]


@pytest.mark.parametrize(("hours", "clash"), [(1, True), (2, False)])
def test_a_team_clashes_until_the_break_after_its_match_ends(hours: int, clash: bool) -> None:
    """The matches take 105 minutes with their break: an hour apart they overlap, two don't."""
    stages = [stage_with_two_matches(DUMMY_MOCK_TIME + timedelta(hours=hours))]
    assert bool(find_conflicts(TOURNAMENT, stages, Lineups({}), Calendar())) is clash


def test_conflicts_follow_teams_across_different_slots() -> None:
    stage = stage_with_two_matches(distinct_slots=True)
    assert find_conflicts(TOURNAMENT, [stage], Lineups({}), Calendar()) == [
        conflict(-1, -1, -2),
        conflict(-2, -1, -1),
    ]


def test_a_team_and_a_player_that_play_in_another_tournament_meanwhile() -> None:
    """
    Team -2 also takes part in the other tournament, and plays there during its match here.
    Alex plays for team -4 here, and for another team there during team -4's match.
    """
    stage = stage_with_two_matches(DUMMY_MOCK_TIME + timedelta(hours=2))
    elsewhere = Calendar()
    elsewhere.book_team(TeamId(-2), booking(-100, 150, 170))
    elsewhere.book_player(ALEX, booking(-101, 30, 50))
    # Bea plays for team -4 too, but has nothing else on.
    lineups = Lineups({TeamId(-4): frozenset({ALEX, BEA})})

    assert find_conflicts(TOURNAMENT, [stage], lineups, elsewhere) == [
        conflict(-1, -2, -100, elsewhere=True),
        conflict(-2, -4, -101, players=[ALEX], elsewhere=True),
    ]


def test_a_booking_that_takes_the_whole_team_is_reported_once() -> None:
    calendar = Calendar()
    both = booking(-100, 0, 30)
    calendar.book_team(TeamId(1), both)
    calendar.book_player(ALEX, both)
    calendar.book_player(BEA, booking(-101, 10, 40))

    clashes = calendar.clashes(
        Competitors(TeamId(1), frozenset({ALEX, BEA})), at(0), at(20), excluding=MatchId(1)
    )

    assert [(clash.booking.match_id, clash.player_ids) for clash in clashes] == [
        (-100, frozenset()),
        (-101, frozenset({BEA})),
    ]


def test_bookings_that_touch_do_not_clash() -> None:
    calendar = Calendar()
    calendar.book_team(TeamId(1), booking(-100, 0, 15))
    side = Competitors(TeamId(1), frozenset())
    assert calendar.clashes(side, at(15), at(30), excluding=MatchId(1)) == []
    assert len(calendar.clashes(side, at(14), at(30), excluding=MatchId(1))) == 1


def brute_force_earliest_start(bookings: list[Booking], not_before: int, minutes: int) -> int:
    """The first whole minute from `not_before` on when a match of `minutes` overlaps nothing."""
    start = not_before
    while any(booking.overlaps(at(start), at(start + minutes)) for booking in bookings):
        start += 1
    return start


@pytest.mark.parametrize("seed", range(50))
def test_the_earliest_start_skips_every_booking_of_the_teams_and_players(seed: int) -> None:
    rng = random.Random(seed)
    calendar = Calendar()
    sides = [
        Competitors(TeamId(1), frozenset({ALEX})),
        Competitors(TeamId(2), frozenset({BEA})),
    ]
    relevant: list[Booking] = []
    for match_id in range(rng.randrange(0, 12)):
        start = rng.randrange(0, 240, 5)
        planned = booking(match_id, start, start + rng.choice((5, 10, 15, 30, 45)))
        who = rng.choice(("team1", "team2", "alex", "bea", "stranger"))
        if who == "team1":
            calendar.book_team(TeamId(1), planned)
        elif who == "team2":
            calendar.book_team(TeamId(2), planned)
        elif who == "alex":
            calendar.book_player(ALEX, planned)
        elif who == "bea":
            calendar.book_player(BEA, planned)
        else:
            calendar.book_player(PlayerId(-99), planned)
        if who != "stranger":
            relevant.append(planned)
    not_before, minutes = rng.randrange(0, 120, 5), rng.choice((10, 20, 40))

    earliest = calendar.earliest_start(sides, at(not_before), minutes)

    assert earliest == at(brute_force_earliest_start(relevant, not_before, minutes))
