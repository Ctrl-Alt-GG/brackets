from heliclockter import datetime_utc

from bracket.models.db.shared import BaseModelORM
from bracket.utils.id_types import ClubId
from bracket.utils.pydantic import Name


class ClubInsertable(BaseModelORM):
    name: str
    created: datetime_utc


class Club(ClubInsertable):
    id: ClubId


class ClubCreateBody(BaseModelORM):
    name: Name


class ClubUpdateBody(BaseModelORM):
    name: Name
