import csv
from decimal import Decimal

from heliclockter import datetime_utc
from pydantic import Field, field_validator

from bracket.models.db.player import Player
from bracket.models.db.shared import BaseModelORM
from bracket.models.results import START_ELO
from bracket.utils.id_types import PlayerId, TeamId, TournamentId
from bracket.utils.pydantic import ParticipantName, check_participant_names


class TeamInsertable(BaseModelORM):
    created: datetime_utc
    name: str
    tournament_id: TournamentId
    active: bool
    # The team's results over the tournament. Repositories read the unmaintained columns of the
    # teams table here; answers that show results replace them with the replayed totals
    # (`bracket.logic.ranking.team_totals`).
    elo_score: Decimal = START_ELO
    swiss_score: Decimal = Decimal("0.0")
    wins: int = 0
    draws: int = 0
    losses: int = 0
    logo_path: str | None = None


class Team(TeamInsertable):
    id: TeamId


class FullTeamWithPlayers(Team):
    """A team with its roster."""

    players: list[Player]

    @property
    def player_ids(self) -> list[PlayerId]:
        return [player.id for player in self.players]


class TeamBody(BaseModelORM):
    name: ParticipantName
    active: bool
    player_ids: set[PlayerId]


def parse_teams_with_players(names: str) -> list[tuple[str, list[str]]]:
    """Every line is a team's name, optionally followed by its players, separated by commas."""
    return [
        (row[0].strip(), [player.strip() for player in row[1:] if player.strip()])
        for row in csv.reader(names.splitlines())
        if any(cell.strip() for cell in row)
    ]


class TeamMultiBody(BaseModelORM):
    names: str = Field(..., min_length=1)
    active: bool

    @field_validator("names")
    @classmethod
    def validate_names(cls, value: str) -> str:
        teams = parse_teams_with_players(value)
        if not teams:
            raise ValueError("Enter at least one team")
        if any(not team_name for team_name, _ in teams):
            raise ValueError("Every line needs a team name before its players")
        check_participant_names([name for team in teams for name in (team[0], *team[1])])
        return value

    @property
    def teams_with_players(self) -> list[tuple[str, list[str]]]:
        return parse_teams_with_players(self.names)
