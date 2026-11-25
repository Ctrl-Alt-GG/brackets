from typing import Self

from heliclockter import datetime_utc
from pydantic import Field, model_validator

from bracket.models.db.shared import BaseModelORM
from bracket.models.db.stage_item_inputs import StageItemInputCreateBody
from bracket.models.enums import StageType
from bracket.utils.i18n import gettext
from bracket.utils.id_types import RankingId, StageId, StageItemId
from bracket.utils.pydantic import Name


class StageItemInsertable(BaseModelORM):
    stage_id: StageId
    name: str
    created: datetime_utc
    type: StageType
    team_count: int = Field(ge=2, le=64)
    # The tournament's ranking whose rules decide the stage item's standings.
    ranking_id: RankingId

    @property
    def label(self) -> str:
        """
        The stage item's name in a message. One named after its format, as those created without
        a name are, is named in the language of the request.
        """
        return (
            self.type.translated_label if self.name in ("", self.type.default_name) else self.name
        )


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
    # Without one, the stage item uses the tournament's first ranking.
    ranking_id: RankingId | None = None

    @model_validator(mode="after")
    def team_count_fits_type(self) -> Self:
        if (
            self.type is StageType.SINGLE_ELIMINATION
            and self.team_count not in SINGLE_ELIMINATION_TEAM_COUNTS
        ):
            counts = ", ".join(str(count) for count in SINGLE_ELIMINATION_TEAM_COUNTS)
            raise ValueError(
                gettext("A single elimination bracket has {counts} teams", counts=counts)
            )
        return self

    def get_name_or_default_name(self) -> str:
        return self.name if self.name is not None else self.type.default_name


class StageItemWithInputsCreate(StageItemCreateBody):
    inputs: list[StageItemInputCreateBody]

    @model_validator(mode="after")
    def inputs_fill_every_slot(self) -> Self:
        if len(self.inputs) != self.team_count:
            raise ValueError(gettext("team_count doesn't match length of inputs"))
        return self
