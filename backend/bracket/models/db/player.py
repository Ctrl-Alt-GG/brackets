from heliclockter import datetime_utc
from pydantic import Field, field_validator

from bracket.models.db.shared import BaseModelORM
from bracket.utils.i18n import gettext
from bracket.utils.id_types import PlayerId
from bracket.utils.pydantic import ParticipantName, check_participant_names


class PlayerInsertable(BaseModelORM):
    name: str
    created: datetime_utc


class Player(PlayerInsertable):
    """
    Someone who plays. Players are shared by every tournament: one takes part in a tournament as an
    active member of one of its teams.
    """

    id: PlayerId


class PlayerBody(BaseModelORM):
    name: ParticipantName


def parse_player_names(names: str) -> list[str]:
    """One player per line."""
    return [name.strip() for name in names.splitlines() if name.strip()]


class PlayerMultiBody(BaseModelORM):
    names: str = Field(..., min_length=1)

    @field_validator("names")
    @classmethod
    def validate_names(cls, value: str) -> str:
        names = parse_player_names(value)
        if not names:
            raise ValueError(gettext("Enter at least one player"))
        check_participant_names(names)
        return value

    @property
    def player_names(self) -> list[str]:
        return parse_player_names(self.names)
