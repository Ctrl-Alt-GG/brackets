from enum import auto
from typing import Any

from heliclockter import datetime_utc
from pydantic import Field, model_validator

from bracket.models.db.shared import BaseModelORM
from bracket.models.db.stage_item_inputs import StageItemInputCreateBody
from bracket.utils.id_types import RankingId, StageId, StageItemId
from bracket.utils.pydantic import Name
from bracket.utils.types import EnumAutoStr


class StageType(EnumAutoStr):
    ROUND_ROBIN = auto()
    SINGLE_ELIMINATION = auto()
    SWISS = auto()

    @property
    def supports_dynamic_number_of_rounds(self) -> bool:
        return self in [StageType.SWISS]


class StageItemInsertable(BaseModelORM):
    stage_id: StageId
    name: str
    created: datetime_utc
    type: StageType
    team_count: int = Field(ge=2, le=64)
    ranking_id: RankingId | None = None


class StageItem(StageItemInsertable):
    id: StageItemId


class StageItemUpdateBody(BaseModelORM):
    name: Name


# A knockout bracket halves every round, so it starts from a power of two.
SINGLE_ELIMINATION_TEAM_COUNTS = (2, 4, 8, 16, 32)


class StageItemCreateBody(BaseModelORM):
    stage_id: StageId
    name: Name | None = None
    type: StageType
    team_count: int = Field(ge=2, le=64)
    ranking_id: RankingId | None = None

    @model_validator(mode="after")
    def team_count_fits_type(self) -> "StageItemCreateBody":
        if (
            self.type is StageType.SINGLE_ELIMINATION
            and self.team_count not in SINGLE_ELIMINATION_TEAM_COUNTS
        ):
            counts = ", ".join(str(count) for count in SINGLE_ELIMINATION_TEAM_COUNTS)
            raise ValueError(f"A single elimination bracket has {counts} teams")
        return self

    def get_name_or_default_name(self) -> str:
        return (
            self.name if self.name is not None else str(self.type.value).replace("_", " ").title()
        )


class StageItemWithInputsCreate(StageItemCreateBody):
    inputs: list[StageItemInputCreateBody]

    def get_name_or_default_name(self) -> str:
        return (
            self.name if self.name is not None else str(self.type.value).replace("_", " ").title()
        )

    @model_validator(mode="before")
    def handle_inputs_length(cls, values: Any) -> Any:
        if ("inputs" in values and "team_count" in values) and (
            len(values["inputs"]) != values["team_count"]
        ):
            raise ValueError("team_count doesn't match length of inputs")
        return values
