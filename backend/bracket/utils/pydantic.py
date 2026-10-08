import re
from typing import Annotated

from pydantic import AfterValidator, StringConstraints

# What a team or player name may be. They are shown in brackets and schedules, so they are short.
PARTICIPANT_NAME_MAX_LENGTH = 30

# A name typed into a form. Surrounding whitespace is dropped and the name can't be blank.
Name = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=100)]
ParticipantName = Annotated[
    str,
    StringConstraints(strip_whitespace=True, min_length=1, max_length=PARTICIPANT_NAME_MAX_LENGTH),
]


DASHBOARD_ENDPOINT_MAX_LENGTH = 64


def validate_dashboard_endpoint(value: str | None) -> str | None:
    """
    A tournament's custom Details link, or `None` without one.

    It is a segment of the page's URL, so only URL-safe characters are allowed. It also needs a
    letter: the frontend reads a link of only digits as a tournament id.
    """
    if value is None or not value.strip():
        return None

    value = value.strip()
    if len(value) > DASHBOARD_ENDPOINT_MAX_LENGTH:
        raise ValueError(
            f"The Details link can be at most {DASHBOARD_ENDPOINT_MAX_LENGTH} characters long"
        )
    if not re.fullmatch(r"[A-Za-z0-9_-]*[A-Za-z][A-Za-z0-9_-]*", value):
        raise ValueError(
            'Use only letters, numbers, "-" and "_" in the Details link, with at least one letter'
        )

    return value


DashboardEndpoint = Annotated[str | None, AfterValidator(validate_dashboard_endpoint)]


def check_participant_names(names: list[str]) -> None:
    for name in names:
        if len(name) > PARTICIPANT_NAME_MAX_LENGTH:
            raise ValueError(
                f'"{name}" is longer than the {PARTICIPANT_NAME_MAX_LENGTH} characters a name '
                "can have"
            )
