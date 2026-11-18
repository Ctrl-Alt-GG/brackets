"""How much an account may create."""

from collections.abc import Mapping
from enum import Enum

from fastapi import HTTPException
from starlette import status

from bracket.models.db.user import UserBase
from bracket.models.enums import UserAccountType


class Limit(Enum):
    """What an account can create a limited number of, in the organizer's words."""

    TEAMS = "teams in a tournament"
    PLAYERS = "players in a tournament"
    # Clubs are called events in the frontend.
    CLUBS = "events"
    TOURNAMENTS = "tournaments in an event"
    STAGES = "stages in a tournament"
    STAGE_ITEMS = "stage items in a tournament"
    # Every round of the tournament counts: those a format creates with its stage item as well as
    # the Swiss rounds an organizer adds one at a time.
    ROUNDS = "rounds in a tournament"
    RANKINGS = "rankings in a tournament"


LIMITS: Mapping[UserAccountType, Mapping[Limit, int]] = {
    UserAccountType.REGULAR: {
        Limit.TEAMS: 128,
        Limit.PLAYERS: 256,
        Limit.CLUBS: 32,
        Limit.TOURNAMENTS: 64,
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
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST,
            f"That would be more than the {maximum} {limit.value} that are allowed.",
        )
