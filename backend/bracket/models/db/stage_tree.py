"""A tournament's stages with their stage items, slots, rounds and matches, as loaded together."""

from pydantic import computed_field

from bracket.models.db.match import MatchWithSlots
from bracket.models.db.round import Round
from bracket.models.db.stage import Stage
from bracket.models.db.stage_item import StageItem
from bracket.models.db.stage_item_inputs import StageItemInput


class RoundWithMatches(Round):
    matches: list[MatchWithSlots]


class StageItemWithRounds(StageItem):
    rounds: list[RoundWithMatches]
    inputs: list[StageItemInput]

    @computed_field  # type: ignore[prop-decorator]
    @property
    def type_name(self) -> str:
        return self.type.display_label


class StageWithStageItems(Stage):
    stage_items: list[StageItemWithRounds]
