from pydantic import EmailStr, field_validator

from bracket.models.db.shared import BaseModelORM
from bracket.models.enums import TournamentRole
from bracket.utils.id_types import UserId
from bracket.utils.security import normalize_email


class Organizer(BaseModelORM):
    """Someone who runs a tournament: its owner, or an account the owner added to help."""

    user_id: UserId
    name: str
    email: str
    role: TournamentRole


class OrganizerCreateBody(BaseModelORM):
    email: EmailStr

    @field_validator("email")
    @classmethod
    def normalize_organizer_email(cls, value: str) -> str:
        return normalize_email(value)


class OwnerUpdateBody(BaseModelORM):
    # One of the tournament's organizers.
    user_id: UserId
