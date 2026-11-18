from collections.abc import Iterator, Mapping
from typing import Any

from bracket.models.db.match import MatchWithSlots
from bracket.models.db.stage_item_inputs import StageItemInput
from bracket.models.db.stage_tree import (
    RoundWithMatches,
    StageItemWithRounds,
    StageWithStageItems,
)
from bracket.utils.id_types import MatchId, RoundId, StageItemId, StageItemInputId

# The match fields that can change without changing which slots the match has, and therefore
# without changing its variant.
_FIELDS_THAT_KEEP_SLOTS = frozenset(
    {
        "start_time",
        "duration_minutes",
        "margin_minutes",
        "custom_duration_minutes",
        "custom_margin_minutes",
        "stage_item_input1_score",
        "stage_item_input2_score",
        "scoreless_result",
        "stage_item_input1_conflict",
        "stage_item_input2_conflict",
    }
)


class TournamentGraph:
    """
    One request's loaded stage tree, with lookups, and the changes to it that keep its copies in
    agreement.

    A slot appears in its stage item's inputs and again inside every match it plays, as separate
    objects. Changes made through this class update every copy, so a command can reuse the tree
    for rankings, scheduling and conflict checks after changing it, instead of loading it again.
    It holds no session: whoever changes the tree writes the same change to the database.
    """

    def __init__(self, stages: list[StageWithStageItems]) -> None:
        self.stages = stages
        self._stage_items = {
            stage_item.id: stage_item for stage in stages for stage_item in stage.stage_items
        }
        self._rounds: dict[RoundId, tuple[StageItemWithRounds, RoundWithMatches]] = {
            round_.id: (stage_item, round_)
            for stage_item in self._stage_items.values()
            for round_ in stage_item.rounds
        }
        # Where each match is: replacing a match keeps its position in its round.
        self._matches: dict[MatchId, tuple[RoundWithMatches, int]] = {
            match.id: (round_, position)
            for _, round_ in self._rounds.values()
            for position, match in enumerate(round_.matches)
        }

    def stage_items(self) -> Iterator[StageItemWithRounds]:
        return iter(self._stage_items.values())

    def stage_item(self, stage_item_id: StageItemId) -> StageItemWithRounds:
        return self._stage_items[stage_item_id]

    def locate_round(self, round_id: RoundId) -> tuple[StageItemWithRounds, RoundWithMatches]:
        """The round and the stage item it belongs to."""
        return self._rounds[round_id]

    def matches(self) -> Iterator[MatchWithSlots]:
        return (round_.matches[position] for round_, position in self._matches.values())

    def match(self, match_id: MatchId) -> MatchWithSlots:
        round_, position = self._matches[match_id]
        return round_.matches[position]

    def slots(self) -> Iterator[StageItemInput]:
        """Every slot once: the copies in the stage items' inputs."""
        return (slot for stage_item in self.stage_items() for slot in stage_item.inputs)

    def update_match(self, match_id: MatchId, **changes: Any) -> None:
        """Change fields of a match that don't change its slots, such as its result or time."""
        if not changes.keys() <= _FIELDS_THAT_KEEP_SLOTS:
            raise ValueError(f"Change slots with replace_matches: {set(changes)}")
        match = self.match(match_id)
        for field, value in changes.items():
            setattr(match, field, value)

    def replace_matches(self, matches: Mapping[MatchId, MatchWithSlots]) -> None:
        """
        Put these matches in place of those with their ids. Build them with
        `bracket.models.db.match.with_slots`, which validates the variant their slots make.
        """
        for match_id, match in matches.items():
            if match.id != match_id:
                raise ValueError(f"Match {match.id} can't replace match {match_id}")
            round_, position = self._matches[match_id]
            round_.matches[position] = match

    def replace_slots(self, slots: Mapping[StageItemInputId, StageItemInput]) -> None:
        """
        Put these slots in place of every copy of those with their ids. A slot keeps its id, so a
        match that plays it keeps its variant.
        """
        for slot_id, slot in slots.items():
            if slot.id != slot_id:
                raise ValueError(f"Slot {slot.id} can't replace slot {slot_id}")
        for stage_item in self.stage_items():
            stage_item.inputs = [slots.get(slot.id, slot) for slot in stage_item.inputs]
        for match in self.matches():
            if match.stage_item_input1_id is not None and match.stage_item_input1_id in slots:
                match.stage_item_input1 = slots[match.stage_item_input1_id]
            if match.stage_item_input2_id is not None and match.stage_item_input2_id in slots:
                match.stage_item_input2 = slots[match.stage_item_input2_id]
