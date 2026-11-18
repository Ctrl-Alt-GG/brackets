from __future__ import annotations

from typing import Any, Self

from heliclockter import datetime_utc, timedelta
from pydantic import (
    BaseModel,
    Field,
    TypeAdapter,
    computed_field,
    field_validator,
    model_validator,
)

from bracket.models.db.shared import BaseModelORM
from bracket.models.db.stage_item_inputs import StageItemInput
from bracket.utils.id_types import MatchId, RoundId, StageItemInputId


class MatchBaseInsertable(BaseModelORM):
    created: datetime_utc
    start_time: datetime_utc | None = None
    duration_minutes: int
    margin_minutes: int
    custom_duration_minutes: int | None = None
    custom_margin_minutes: int | None = None
    round_id: RoundId
    stage_item_input1_score: int
    stage_item_input2_score: int
    stage_item_input1_conflict: bool
    stage_item_input2_conflict: bool
    # Scores are the result, and an unplayed match reads 0-0. This marks a 0-0 that was played.
    scoreless_result: bool = False

    @property
    def end_time(self) -> datetime_utc:
        assert self.start_time
        return self.start_time + timedelta(minutes=self.duration_minutes + self.margin_minutes)

    @computed_field  # type: ignore[prop-decorator]
    @property
    def played(self) -> bool:
        """Whether the match has a result."""
        return is_played(self)


def is_played(match: MatchBaseInsertable) -> bool:
    return (
        match.stage_item_input1_score != 0
        or match.stage_item_input2_score != 0
        or match.scoreless_result
    )


class MatchInsertable(MatchBaseInsertable):
    stage_item_input1_id: StageItemInputId | None = None
    stage_item_input2_id: StageItemInputId | None = None
    stage_item_input1_winner_from_match_id: MatchId | None = None
    stage_item_input2_winner_from_match_id: MatchId | None = None


class Match(MatchInsertable):
    id: MatchId
    stage_item_input1: StageItemInput | None = None
    stage_item_input2: StageItemInput | None = None

    def get_winner(self) -> StageItemInput | None:
        if self.stage_item_input1_score > self.stage_item_input2_score:
            return self.stage_item_input1
        if self.stage_item_input1_score < self.stage_item_input2_score:
            return self.stage_item_input2

        return None


def _check_slots_match_ids(match: Match) -> None:
    """A loaded slot is the one its id names, and an id without a slot has none."""
    for position, input_id, input_ in (
        (1, match.stage_item_input1_id, match.stage_item_input1),
        (2, match.stage_item_input2_id, match.stage_item_input2),
    ):
        if (input_.id if input_ is not None else None) != input_id:
            raise ValueError(
                f"stage_item_input{position} doesn't match stage_item_input{position}_id"
            )


class MatchWithDetails(Match):
    """
    A match with its slots loaded, of which at most one is known yet: a knockout match that waits
    for the winner of an earlier match.
    """

    @model_validator(mode="after")
    def at_most_one_slot(self) -> Self:
        _check_slots_match_ids(self)
        if self.stage_item_input1 is not None and self.stage_item_input2 is not None:
            raise ValueError("A match with both slots known is a MatchWithDetailsDefinitive")
        return self


class MatchWithDetailsDefinitive(Match):
    """
    A match with both of its slots known. Those can still be slots that wait for a team to
    advance from an earlier stage.
    """

    stage_item_input1_id: StageItemInputId  # pyrefly: ignore [bad-override]
    stage_item_input2_id: StageItemInputId  # pyrefly: ignore [bad-override]
    stage_item_input1: StageItemInput  # pyrefly: ignore [bad-override]
    stage_item_input2: StageItemInput  # pyrefly: ignore [bad-override]

    @model_validator(mode="after")
    def slots_match_ids(self) -> Self:
        _check_slots_match_ids(self)
        return self

    @property
    def stage_item_inputs(self) -> list[StageItemInput]:
        return [self.stage_item_input1, self.stage_item_input2]

    @property
    def stage_item_input_ids(self) -> list[StageItemInputId]:
        return [self.stage_item_input1_id, self.stage_item_input2_id]


MatchWithSlots = MatchWithDetailsDefinitive | MatchWithDetails
_match_with_slots: TypeAdapter[MatchWithSlots] = TypeAdapter(MatchWithSlots)


def with_slots(
    match: Match,
    stage_item_input1: StageItemInput | None,
    stage_item_input2: StageItemInput | None,
    **changes: Any,
) -> MatchWithSlots:
    """
    The match with these slots, and any other `changes`, as the variant the slots make it.

    Filling or clearing a slot can turn one variant into the other. Every such change goes through
    here, so that the result is validated like a match loaded from the database.
    """
    return _match_with_slots.validate_python(
        match.model_dump()
        | {
            "stage_item_input1_id": stage_item_input1.id if stage_item_input1 else None,
            "stage_item_input2_id": stage_item_input2.id if stage_item_input2 else None,
            "stage_item_input1": stage_item_input1,
            "stage_item_input2": stage_item_input2,
        }
        | changes
    )


# Far above any real score, and far below what the database column holds.
MAX_SCORE = 100_000
# A day: longer than any match or break.
MAX_MINUTES = 24 * 60


class MatchBody(BaseModelORM):
    stage_item_input1_score: int = Field(default=0, ge=0, le=MAX_SCORE)
    stage_item_input2_score: int = Field(default=0, ge=0, le=MAX_SCORE)
    # Saving 0-0 normally means "not played yet". Set this to record a match that ended 0-0.
    scoreless_result: bool = False
    custom_duration_minutes: int | None = Field(default=None, ge=1, le=MAX_MINUTES)
    custom_margin_minutes: int | None = Field(default=None, ge=0, le=MAX_MINUTES)

    @model_validator(mode="after")
    def normalize_scoreless_result(self) -> Self:
        if self.stage_item_input1_score or self.stage_item_input2_score:
            self.scoreless_result = False
        return self

    @property
    def has_result(self) -> bool:
        return bool(
            self.stage_item_input1_score or self.stage_item_input2_score or self.scoreless_result
        )


class ScheduleDelayBody(BaseModelORM):
    minutes: int = Field(ge=-MAX_MINUTES, le=MAX_MINUTES)

    @field_validator("minutes")
    @classmethod
    def minutes_move_something(cls, value: int) -> int:
        if value == 0:
            raise ValueError("Enter how many minutes to move the schedule by")
        return value


class MatchCreateBodyFrontend(BaseModelORM):
    round_id: RoundId
    stage_item_input1_id: StageItemInputId | None = None
    stage_item_input2_id: StageItemInputId | None = None
    stage_item_input1_winner_from_match_id: MatchId | None = None
    stage_item_input2_winner_from_match_id: MatchId | None = None


class MatchCreateBody(MatchCreateBodyFrontend):
    duration_minutes: int
    margin_minutes: int
    custom_duration_minutes: int | None = None
    custom_margin_minutes: int | None = None


class MatchTiming(BaseModel):
    match_id: MatchId
    start_time: datetime_utc
    duration_minutes: int
    margin_minutes: int
