from uuid import uuid4
from zoneinfo import ZoneInfo

from heliclockter import datetime_utc

from bracket.models.db.account import UserAccountType
from bracket.models.db.user import User, UserInDB, UserInsertable
from bracket.routes.auth import create_access_token
from bracket.utils.types import assert_some

MOCK_NOW = datetime_utc(
    year=2200, month=1, day=1, hour=0, minute=0, microsecond=0, second=0, tzinfo=ZoneInfo("UTC")
)


def generate_email() -> str:
    return f"donald_duck-{uuid4()}@example.org"


def get_mock_user() -> UserInsertable:
    return UserInsertable(
        email=generate_email(),
        name="Donald Duck",
        # hash of 'mypassword'
        password_hash="$2b$12$.LcTJuoOtwU4CfK8UgEtIu5BRmTdvZv6IH.6IvGshDCgwJsvOMLeu",
        created=datetime_utc(year=2000, month=1, day=1, tzinfo=ZoneInfo("UTC")),
        account_type=UserAccountType.REGULAR,
    )


def get_mock_token(user: User | UserInDB) -> str:
    return create_access_token(user.id, assert_some(user.password_hash))
