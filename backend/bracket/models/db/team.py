import csv

from heliclockter import datetime_utc
from pydantic import AliasPath, ConfigDict, Field, field_validator

from bracket.models.db.player import Player
from bracket.models.db.shared import ApiModel, BaseModelORM
from bracket.models.enums import TournamentStatus
from bracket.utils.i18n import gettext
from bracket.utils.id_types import PlayerId, TeamId, TournamentId
from bracket.utils.pydantic import ParticipantName, check_participant_names


class TeamInsertable(BaseModelORM):
    name: str
    created: datetime_utc
    logo_path: str | None = None


class Team(TeamInsertable):
    """A team. Teams are shared by every tournament, and can take part in several at once."""

    id: TeamId


class TeamMember(BaseModelORM):
    """A player in a team's roster."""

    player: Player
    # Only active members play for the team. A player is an active member of one team at most
    # among the teams of a tournament.
    active: bool


class TeamParticipation(BaseModelORM):
    """A tournament that a team takes part in."""

    model_config = ConfigDict(validate_by_name=True, validate_by_alias=True)

    tournament_id: TournamentId
    tournament_name: str = Field(validation_alias=AliasPath("tournament", "name"))
    tournament_status: TournamentStatus = Field(validation_alias=AliasPath("tournament", "status"))
    # Whether the team takes part in the tournament's rounds that are still to come.
    active: bool


class TeamWithMembers(Team):
    """A team with its roster and the tournaments it takes part in."""

    members: list[TeamMember]
    participations: list[TeamParticipation]


class TeamMemberBody(ApiModel):
    player_id: PlayerId
    active: bool = True


class TeamBody(BaseModelORM):
    name: ParticipantName
    members: list[TeamMemberBody] = Field(default_factory=list)

    @field_validator("members")
    @classmethod
    def players_are_members_once(cls, members: list[TeamMemberBody]) -> list[TeamMemberBody]:
        if len({member.player_id for member in members}) < len(members):
            raise ValueError(gettext("A player can be in a team's roster once"))
        return members


def parse_teams_with_players(names: str) -> list[tuple[str, list[str]]]:
    """Every line is a team's name, optionally followed by its players, separated by commas."""
    return [
        (row[0].strip(), [player.strip() for player in row[1:] if player.strip()])
        for row in csv.reader(names.splitlines())
        if any(cell.strip() for cell in row)
    ]


class TeamMultiBody(BaseModelORM):
    names: str = Field(..., min_length=1)

    @field_validator("names")
    @classmethod
    def validate_names(cls, value: str) -> str:
        teams = parse_teams_with_players(value)
        if not teams:
            raise ValueError(gettext("Enter at least one team"))
        if any(not team_name for team_name, _ in teams):
            raise ValueError(gettext("Every line needs a team name before its players"))
        check_participant_names([name for team in teams for name in (team[0], *team[1])])
        return value

    @property
    def teams_with_players(self) -> list[tuple[str, list[str]]]:
        return parse_teams_with_players(self.names)
