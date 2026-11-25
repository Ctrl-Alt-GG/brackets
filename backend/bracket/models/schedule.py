"""What is worked out from the schedules of the tournaments that share teams and players."""

from typing import NamedTuple

from heliclockter import datetime_utc

from bracket.models.db.shared import ApiModel
from bracket.utils.id_types import MatchId, PlayerId, TeamId, TournamentId


class MatchElsewhere(NamedTuple):
    """
    A published match of another open tournament, for one of its teams that also takes part in
    this tournament, or for a player who plays for that team there and in this tournament too.
    """

    match_id: MatchId
    tournament_id: TournamentId
    tournament_name: str
    start_time: datetime_utc
    # Including the break after the match.
    minutes: int
    team_id: TeamId
    # Whether `team_id` takes part in this tournament as well.
    team_takes_part: bool
    # A player of this tournament's lineup who plays the match, or `None`.
    player_id: PlayerId | None


class ScheduleConflict(ApiModel):
    """
    A team of a match that has to be somewhere else at the same time: the team, or some of its
    players, play another match then. The other match can be in this tournament or in another one
    that shares the team or the players.
    """

    match_id: MatchId
    team_id: TeamId
    # The team's players who play the other match, for another team. Empty when the team itself
    # plays it.
    player_ids: list[PlayerId]
    other_match_id: MatchId
    other_tournament_id: TournamentId
    other_tournament_name: str
