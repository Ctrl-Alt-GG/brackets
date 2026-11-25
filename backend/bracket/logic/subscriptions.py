"""How much an account may create."""

from collections.abc import Mapping
from enum import Enum

from fastapi import HTTPException
from starlette import status

from bracket.models.db.user import UserBase
from bracket.models.enums import UserAccountType
from bracket.utils.i18n import gettext, gettext_noop


class Limit(Enum):
    """
    What an account can create a limited number of, by the message that refuses one more. It
    says how many are allowed in the organizer's words.
    """

    TEAMS = gettext_noop(
        "That would be more than the {maximum} teams in a tournament that are allowed."
    )
    # Active and inactive members together.
    PLAYERS = gettext_noop(
        "That would be more than the {maximum} players in a team that are allowed."
    )
    # The tournaments an account owns. Those it only helps run don't count.
    TOURNAMENTS = gettext_noop(
        "That would be more than the {maximum} tournaments an account can own."
    )
    STAGES = gettext_noop(
        "That would be more than the {maximum} stages in a tournament that are allowed."
    )
    STAGE_ITEMS = gettext_noop(
        "That would be more than the {maximum} stage items in a tournament that are allowed."
    )
    # Every round of the tournament counts: those a format creates with its stage item as well as
    # the Swiss rounds an organizer adds one at a time.
    ROUNDS = gettext_noop(
        "That would be more than the {maximum} rounds in a tournament that are allowed."
    )
    RANKINGS = gettext_noop(
        "That would be more than the {maximum} rankings in a tournament that are allowed."
    )


LIMITS: Mapping[UserAccountType, Mapping[Limit, int]] = {
    UserAccountType.REGULAR: {
        Limit.TEAMS: 128,
        Limit.PLAYERS: 64,
        Limit.TOURNAMENTS: 1024,
        Limit.STAGES: 16,
        Limit.STAGE_ITEMS: 64,
        Limit.ROUNDS: 64,
        Limit.RANKINGS: 16,
    }
}


def check_requirement(
    limit: Limit, existing_count: int, user: UserBase, additions: int = 1
) -> None:
    """Refuse to create `additions` more when the account already has `existing_count`."""
    maximum = LIMITS[user.account_type][limit]
    if additions > 0 and existing_count + additions > maximum:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, gettext(limit.value, maximum=maximum))
