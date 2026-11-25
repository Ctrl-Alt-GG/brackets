import re
from typing import Annotated

from pydantic import AfterValidator, StringConstraints

from bracket.utils.i18n import gettext

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
    letter: the frontend reads a link of only digits as a tournament id. It is stored in lowercase
    and looked up in any case, so a link typed with other capitals still works, and two links
    can't differ only by case.
    """
    if value is None or not value.strip():
        return None

    value = value.strip().lower()
    if len(value) > DASHBOARD_ENDPOINT_MAX_LENGTH:
        raise ValueError(
            gettext(
                "The Details link can be at most {maximum} characters long",
                maximum=DASHBOARD_ENDPOINT_MAX_LENGTH,
            )
        )
    if not re.fullmatch(r"[a-z0-9_-]*[a-z][a-z0-9_-]*", value):
        raise ValueError(
            gettext(
                'Use only letters, numbers, "-" and "_" in the Details link, with at least one '
                "letter"
            )
        )

    return value


DashboardEndpoint = Annotated[str | None, AfterValidator(validate_dashboard_endpoint)]


def check_participant_names(names: list[str]) -> None:
    for name in names:
        if len(name) > PARTICIPANT_NAME_MAX_LENGTH:
            raise ValueError(
                gettext(
                    '"{name}" is longer than the {maximum} characters a name can have',
                    maximum=PARTICIPANT_NAME_MAX_LENGTH,
                    name=name,
                )
            )
