import pytest
from fastapi import HTTPException

from bracket.logic.subscriptions import LIMITS, Limit, check_requirement
from bracket.models.db.user import UserPublic
from bracket.models.enums import UserAccountType
from bracket.utils.id_types import UserId
from tests.dummy_records import DUMMY_MOCK_TIME

USER = UserPublic(
    id=UserId(1),
    email="organizer@example.org",
    name="Organizer",
    created=DUMMY_MOCK_TIME,
    account_type=UserAccountType.REGULAR,
)
MAXIMUM = LIMITS[UserAccountType.REGULAR][Limit.TEAMS]


@pytest.mark.parametrize(
    ("existing", "additions"),
    [
        (0, 1),
        (MAXIMUM - 1, 1),
        (MAXIMUM - 3, 3),
        # Creating nothing more is never refused, also above a limit that was lowered since.
        (MAXIMUM + 5, 0),
    ],
)
def test_creating_up_to_the_limit(existing: int, additions: int) -> None:
    check_requirement(Limit.TEAMS, existing, USER, additions)


@pytest.mark.parametrize(("existing", "additions"), [(MAXIMUM, 1), (MAXIMUM - 2, 3)])
def test_creating_past_the_limit(existing: int, additions: int) -> None:
    with pytest.raises(HTTPException) as refused:
        check_requirement(Limit.TEAMS, existing, USER, additions)
    assert refused.value.status_code == 400
    assert refused.value.detail == (
        f"That would be more than the {MAXIMUM} teams in a tournament that are allowed."
    )
