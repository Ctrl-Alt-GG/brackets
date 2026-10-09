from heliclockter import datetime_utc

from bracket.models.db.shared import BaseModelORM
from bracket.utils.id_types import RoundId, StageItemId
from bracket.utils.pydantic import Name


class RoundInsertable(BaseModelORM):
    created: datetime_utc
    stage_item_id: StageItemId
    is_draft: bool
    name: str


class Round(RoundInsertable):
    id: RoundId


class RoundUpdateBody(BaseModelORM):
    name: Name
    is_draft: bool


class RoundCreateBody(BaseModelORM):
    name: Name | None = None
    stage_item_id: StageItemId
