from __future__ import annotations

from typing import TYPE_CHECKING, Any

from fastapi import HTTPException
from pydantic import BaseModel
from starlette import status

if TYPE_CHECKING:
    from bracket.models.db.user import UserBase


class Subscription(BaseModel):
    max_teams: int
    max_players: int
    max_clubs: int
    max_tournaments: int
    max_courts: int
    max_stages: int
    max_stage_items: int
    max_rounds: int
    max_rankings: int


regular_subscription = Subscription(
    max_teams=128,
    max_players=256,
    max_clubs=32,
    max_tournaments=64,
    max_courts=32,
    max_stages=16,
    max_stage_items=64,
    max_rounds=64,
    max_rankings=16,
)

subscription_lookup = {"REGULAR": regular_subscription}

# `clubs` is presented as "events" in the UI.
subscription_attribute_labels = {"max_clubs": "events"}


def check_requirement(array: list[Any], user: UserBase, attribute: str, additions: int = 1) -> None:
    subscription = subscription_lookup[user.account_type.value]
    constraint: int = getattr(subscription, attribute)
    if len(array) + additions > constraint:
        label = subscription_attribute_labels.get(attribute, attribute.replace("max_", ""))
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST,
            f"Your `{user.account_type.value}` subscription allows a maximum of "
            f"{constraint} {label}.",
        )
