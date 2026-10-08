from typing import Literal

from heliclockter import datetime_utc
from pydantic import Field

from bracket.models.db.shared import BaseModelORM
from bracket.utils.id_types import StageId, TournamentId
from bracket.utils.pydantic import Name


class StageInsertable(BaseModelORM):
    tournament_id: TournamentId
    name: str
    created: datetime_utc
    is_active: bool
    custom_duration_minutes: int | None = Field(default=None, ge=1)


class Stage(StageInsertable):
    id: StageId


class StageUpdateBody(BaseModelORM):
    name: Name
    custom_duration_minutes: int | None = Field(default=None, ge=1)


class StageActivateBody(BaseModelORM):
    direction: Literal["next", "previous"] = "next"
