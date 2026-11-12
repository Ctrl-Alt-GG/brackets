from heliclockter import datetime_utc, timedelta
from pydantic import BaseModel, Field, computed_field, field_validator

from bracket.models.db.shared import BaseModelORM
from bracket.models.db.stage_item_inputs import StageItemInput
from bracket.utils.id_types import MatchId, RoundId, StageItemInputId
from bracket.utils.types import assert_some


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


class MatchWithDetails(Match):
    """
    MatchWithDetails has zero or one defined stage item inputs, but not both.
    """


def get_match_hash(
    stage_item_input1_id: StageItemInputId | None, stage_item_input2_id: StageItemInputId | None
) -> str:
    return f"{stage_item_input1_id}-{stage_item_input2_id}"


class MatchWithDetailsDefinitive(Match):
    stage_item_input1: StageItemInput  # pyrefly: ignore [bad-override]
    stage_item_input2: StageItemInput  # pyrefly: ignore [bad-override]

    @property
    def stage_item_inputs(self) -> list[StageItemInput]:
        return [self.stage_item_input1, self.stage_item_input2]

    @property
    def stage_item_input_ids(self) -> list[StageItemInputId]:
        return [assert_some(self.stage_item_input1_id), assert_some(self.stage_item_input2_id)]

    def get_input_ids_hashes(self) -> list[str]:
        return [
            get_match_hash(self.stage_item_input1_id, self.stage_item_input2_id),
            get_match_hash(self.stage_item_input2_id, self.stage_item_input1_id),
        ]


# Far above any real score, and far below what the database column holds.
MAX_SCORE = 100_000
# A day: longer than any match or break.
MAX_MINUTES = 24 * 60


class MatchBody(BaseModelORM):
    stage_item_input1_score: int = Field(0, ge=0, le=MAX_SCORE)
    stage_item_input2_score: int = Field(0, ge=0, le=MAX_SCORE)
    # Saving 0-0 normally means "not played yet". Set this to record a match that ended 0-0.
    scoreless_result: bool = False
    custom_duration_minutes: int | None = Field(None, ge=1, le=MAX_MINUTES)
    custom_margin_minutes: int | None = Field(None, ge=0, le=MAX_MINUTES)


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
