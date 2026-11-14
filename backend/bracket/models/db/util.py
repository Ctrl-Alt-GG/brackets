from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from pydantic import model_validator

from bracket.models.db.match import MatchWithDetails, MatchWithDetailsDefinitive
from bracket.models.db.round import Round
from bracket.models.db.stage import Stage
from bracket.models.db.stage_item import StageItem, StageType
from bracket.models.db.stage_item_inputs import StageItemInput


class RoundWithMatches(Round):
    matches: list[MatchWithDetailsDefinitive | MatchWithDetails]


class StageItemWithRounds(StageItem):
    rounds: list[RoundWithMatches]
    inputs: list[StageItemInput]
    type_name: str

    @model_validator(mode="before")
    @classmethod
    def fill_type_name(cls, values: Any) -> Any:
        if isinstance(values, Mapping):
            type_ = values["type"]
            name = type_.value if isinstance(type_, StageType) else type_
            return {**values, "type_name": name.lower().capitalize().replace("_", " ")}
        return values


class StageWithStageItems(Stage):
    stage_items: list[StageItemWithRounds]
