"""Teams and players as they take part in a tournament."""

from heliclockter import datetime_utc
from pydantic import AliasPath, ConfigDict, Field

from bracket.models.db.player import Player
from bracket.models.db.shared import BaseModelORM
from bracket.models.results import ResultTotals
from bracket.utils.id_types import PlayerId, TeamId, TournamentId


class TournamentTeam(BaseModelORM, ResultTotals):
    """
    A team as it takes part in a tournament, with its results there.

    It is read from the team's participation in the tournament, which holds the team itself. The
    results are replayed from the matches (`bracket.logic.ranking.team_totals`); until then, they
    are those of a team that hasn't played.
    """

    model_config = ConfigDict(validate_by_name=True, validate_by_alias=True)

    id: TeamId = Field(validation_alias=AliasPath("team", "id"))
    name: str = Field(validation_alias=AliasPath("team", "name"))
    created: datetime_utc = Field(validation_alias=AliasPath("team", "created"))
    logo_path: str | None = Field(default=None, validation_alias=AliasPath("team", "logo_path"))
    tournament_id: TournamentId
    # Whether the team plays the rounds that are still to come. Swiss rounds pair active teams.
    active: bool


class TournamentTeamWithPlayers(TournamentTeam):
    """A team with the players who play for it in the tournament: its lineup."""

    players: list[Player]

    @property
    def player_ids(self) -> list[PlayerId]:
        return [player.id for player in self.players]


class TournamentPlayer(Player, ResultTotals):
    """A player as they take part in a tournament: the team they play for, and their results."""

    team_id: TeamId


class TournamentTeamsBody(BaseModelORM):
    """Teams to take part in a tournament."""

    team_ids: set[TeamId] = Field(min_length=1)


class TournamentTeamBody(BaseModelORM):
    active: bool
