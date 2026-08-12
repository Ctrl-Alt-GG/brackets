from __future__ import annotations

from typing import TYPE_CHECKING, Annotated

from heliclockter import datetime_utc
from pydantic import BaseModel, EmailStr, StringConstraints, field_validator, model_validator

from bracket.models.db.account import UserAccountType
from bracket.models.db.shared import BaseModelORM
from bracket.utils.id_types import UserId
from bracket.utils.security import normalize_email, validate_password_strength

if TYPE_CHECKING:
    from bracket.logic.subscriptions import Subscription


class UserBase(BaseModelORM):
    email: EmailStr
    name: str
    created: datetime_utc
    account_type: UserAccountType

    @field_validator("email")
    @classmethod
    def normalize_user_email(cls, value: str) -> str:
        return normalize_email(value)

    @property
    def subscription(self) -> Subscription:
        from bracket.logic.subscriptions import subscription_lookup

        return subscription_lookup[self.account_type.value]


class UserInsertable(UserBase):
    password_hash: str | None = None


class User(UserBase):
    id: UserId
    password_hash: str | None = None


class UserPublic(UserBase):
    id: UserId


class UserToUpdate(BaseModel):
    email: EmailStr
    name: str

    @field_validator("email")
    @classmethod
    def normalize_updated_email(cls, value: str) -> str:
        return normalize_email(value)


class UserPasswordToUpdate(BaseModel):
    password: Annotated[str, StringConstraints(min_length=12, max_length=72)]

    @field_validator("password")
    @classmethod
    def validate_updated_password(cls, value: str) -> str:
        return validate_password_strength(value)


class UserToRegister(BaseModelORM):
    email: EmailStr
    name: str
    password: str

    @field_validator("email")
    @classmethod
    def normalize_registration_email(cls, value: str) -> str:
        return normalize_email(value)

    @model_validator(mode="after")
    def validate_registration_password(self) -> UserToRegister:
        self.password = validate_password_strength(self.password, (self.email, self.name))
        return self


class UserInDB(UserBase):
    id: UserId
    password_hash: str
