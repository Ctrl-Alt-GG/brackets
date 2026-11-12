from heliclockter import datetime_utc
from pydantic import EmailStr, field_validator

from bracket.models.db.shared import BaseModelORM
from bracket.models.db.user_x_club import UserXClubRelation
from bracket.utils.id_types import ClubId, UserId
from bracket.utils.pydantic import Name
from bracket.utils.security import normalize_email


class ClubInsertable(BaseModelORM):
    name: str
    created: datetime_utc


class Club(ClubInsertable):
    id: ClubId


class ClubCreateBody(BaseModelORM):
    name: Name


class ClubUpdateBody(BaseModelORM):
    name: Name


class ClubMember(BaseModelORM):
    """An organizer of an event: its owner, or someone the owner added to help run it."""

    user_id: UserId
    name: str
    email: str
    relation: UserXClubRelation


class ClubMemberCreateBody(BaseModelORM):
    email: EmailStr

    @field_validator("email")
    @classmethod
    def normalize_member_email(cls, value: str) -> str:
        return normalize_email(value)
