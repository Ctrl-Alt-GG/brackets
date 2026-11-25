"""
When teams and players are taken by matches.

Teams and players can take part in several tournaments at once, but they play one match at a
time. A `Calendar` holds the matches that take each of them, so that the planner can start a match
once everyone in it is free, and the schedule can show the matches that still clash.
"""

from collections import defaultdict
from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from typing import Self

from heliclockter import datetime_utc, timedelta

from bracket.models.db.match import MatchWithSlots
from bracket.models.db.stage_item_inputs import StageItemInputFinal
from bracket.models.schedule import MatchElsewhere
from bracket.utils.id_types import MatchId, PlayerId, TeamId, TournamentId


@dataclass(frozen=True, slots=True)
class Booking:
    """A match, which takes its teams and their players from its start until its break ends."""

    match_id: MatchId
    tournament_id: TournamentId
    tournament_name: str
    start: datetime_utc
    end: datetime_utc

    def overlaps(self, start: datetime_utc, end: datetime_utc) -> bool:
        return self.start < end and start < self.end


@dataclass(frozen=True, slots=True)
class Competitors:
    """A team of a match, and the players who play for it in the match's tournament."""

    team_id: TeamId
    player_ids: frozenset[PlayerId]


@dataclass(frozen=True, slots=True)
class Clash:
    """A booking that takes a team, or some of its players, while they should play a match."""

    booking: Booking
    # The players of the team that the booking takes. Empty when it takes the team itself.
    player_ids: frozenset[PlayerId]


class Lineups:
    """Who plays for each team of a tournament."""

    def __init__(self, players_by_team: Mapping[TeamId, frozenset[PlayerId]]) -> None:
        self._players_by_team = players_by_team

    def competitors(self, match: MatchWithSlots) -> list[Competitors]:
        """The teams of the match that are known, with their players."""
        return [
            Competitors(slot.team_id, self._players_by_team.get(slot.team_id, frozenset()))
            for slot in (match.stage_item_input1, match.stage_item_input2)
            if isinstance(slot, StageItemInputFinal)
        ]


class Calendar:
    """The bookings of teams and of players."""

    def __init__(self) -> None:
        self._by_team: defaultdict[TeamId, dict[MatchId, Booking]] = defaultdict(dict)
        self._by_player: defaultdict[PlayerId, dict[MatchId, Booking]] = defaultdict(dict)

    @classmethod
    def of_matches_elsewhere(cls, matches: Iterable[MatchElsewhere]) -> Self:
        """What other tournaments take of a tournament's teams and players."""
        calendar = cls()
        for match in matches:
            booking = Booking(
                match_id=match.match_id,
                tournament_id=match.tournament_id,
                tournament_name=match.tournament_name,
                start=match.start_time,
                end=match.start_time + timedelta(minutes=match.minutes),
            )
            if match.team_takes_part:
                calendar.book_team(match.team_id, booking)
            if match.player_id is not None:
                calendar.book_player(match.player_id, booking)
        return calendar

    def book_team(self, team_id: TeamId, booking: Booking) -> None:
        self._by_team[team_id][booking.match_id] = booking

    def book_player(self, player_id: PlayerId, booking: Booking) -> None:
        self._by_player[player_id][booking.match_id] = booking

    def _bookings(self, sides: Iterable[Competitors]) -> list[Booking]:
        """Every booking of the sides' teams and players once, in the order they start."""
        bookings: dict[MatchId, Booking] = {}
        for side in sides:
            bookings.update(self._by_team.get(side.team_id, {}))
            for player_id in side.player_ids:
                bookings.update(self._by_player.get(player_id, {}))
        return sorted(bookings.values(), key=lambda booking: booking.start)

    def earliest_start(
        self, sides: Iterable[Competitors], not_before: datetime_utc, minutes: int
    ) -> datetime_utc:
        """
        The earliest time from `not_before` on when a match of `minutes` finds all of its teams
        and their players free.

        The bookings are swept in the order they start, and the match moves to the end of every
        booking it would overlap. A booking that ended before the match's current start can't
        overlap it any more, because the start only moves later.
        """
        start = not_before
        length = timedelta(minutes=minutes)
        for booking in self._bookings(sides):
            if booking.start >= start + length:
                break
            if booking.end > start:
                start = booking.end
        return start

    def clashes(
        self, side: Competitors, start: datetime_utc, end: datetime_utc, *, excluding: MatchId
    ) -> list[Clash]:
        """The bookings other than the match `excluding` that take the side in that time."""
        team_bookings = {
            match_id: booking
            for match_id, booking in self._by_team.get(side.team_id, {}).items()
            if match_id != excluding and booking.overlaps(start, end)
        }
        clashes = [Clash(booking, frozenset()) for booking in team_bookings.values()]

        players_per_booking: defaultdict[MatchId, set[PlayerId]] = defaultdict(set)
        player_bookings: dict[MatchId, Booking] = {}
        for player_id in side.player_ids:
            for match_id, booking in self._by_player.get(player_id, {}).items():
                if (
                    match_id != excluding
                    and match_id not in team_bookings
                    and booking.overlaps(start, end)
                ):
                    players_per_booking[match_id].add(player_id)
                    player_bookings[match_id] = booking
        clashes.extend(
            Clash(booking, frozenset(players_per_booking[match_id]))
            for match_id, booking in player_bookings.items()
        )
        return sorted(clashes, key=lambda clash: (clash.booking.start, clash.booking.match_id))
