from decimal import Decimal

from heliclockter import datetime_utc
from pydantic import Field, field_validator

from bracket.models.db.shared import BaseModelORM
from bracket.utils.id_types import PlayerId, TournamentId
from bracket.utils.pydantic import ParticipantName, check_participant_names


class PlayerInsertable(BaseModelORM):
    active: bool
    name: str
    created: datetime_utc
    tournament_id: TournamentId
    elo_score: Decimal = Decimal("0.0")
    swiss_score: Decimal = Decimal("0.0")
    wins: int = 0
    draws: int = 0
    losses: int = 0


class Player(PlayerInsertable):
    id: PlayerId

    def __hash__(self) -> int:
        return self.id


class PlayerBody(BaseModelORM):
    name: ParticipantName
    active: bool


def parse_player_names(names: str) -> list[str]:
    """One player per line."""
    return [name.strip() for name in names.splitlines() if name.strip()]


class PlayerMultiBody(BaseModelORM):
    names: str = Field(..., min_length=1)
    active: bool

    @field_validator("names")
    @classmethod
    def validate_names(cls, value: str) -> str:
        names = parse_player_names(value)
        if not names:
            raise ValueError("Enter at least one player")
        check_participant_names(names)
        return value

    @property
    def player_names(self) -> list[str]:
        return parse_player_names(self.names)


class PlayerToInsert(PlayerBody):
    created: datetime_utc
    tournament_id: TournamentId
    elo_score: Decimal = Decimal("1200.0")
    swiss_score: Decimal
    wins: int = 0
    draws: int = 0
    losses: int = 0
