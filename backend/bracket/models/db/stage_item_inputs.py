from decimal import Decimal

from pydantic import Field

from bracket.models.db.shared import ApiModel, BaseModelORM
from bracket.models.db.team import Team
from bracket.utils.id_types import StageItemId, StageItemInputId, TeamId, TournamentId


class StageItemInputBase(BaseModelORM):
    """A slot of a stage item. Its variants say what fills it."""

    id: StageItemInputId
    slot: int
    tournament_id: TournamentId
    stage_item_id: StageItemId
    # Results stored with the slot when one of its matches changes. Swiss pairing reads the
    # rating from `points`; standings replay the matches instead.
    points: Decimal = Decimal("0.0")
    wins: int = 0
    draws: int = 0
    losses: int = 0


class StageItemInputTentative(StageItemInputBase):
    """Takes the team at a place of an earlier stage item once that stage is decided."""

    team_id: None = None
    winner_from_stage_item_id: StageItemId
    winner_position: int = Field(ge=1)

    def get_lookup_key(self) -> tuple[StageItemId, int]:
        return self.winner_from_stage_item_id, self.winner_position


class StageItemInputFinal(StageItemInputBase):
    """Has a team, assigned by an organizer or advanced from an earlier stage item."""

    team_id: TeamId
    winner_from_stage_item_id: StageItemId | None = None
    winner_position: int | None = None
    team: Team


class StageItemInputEmpty(StageItemInputBase):
    """Open: nothing fills it yet."""

    team_id: None = None
    winner_from_stage_item_id: None = None
    winner_position: None = None


StageItemInput = StageItemInputTentative | StageItemInputFinal | StageItemInputEmpty


class StageItemInputCreateBodyTentative(ApiModel):
    slot: int
    winner_from_stage_item_id: StageItemId
    winner_position: int = Field(ge=1)


class StageItemInputCreateBodyFinal(ApiModel):
    slot: int
    team_id: TeamId


class StageItemInputCreateBodyEmpty(ApiModel):
    slot: int


StageItemInputCreateBody = (
    StageItemInputCreateBodyTentative
    | StageItemInputCreateBodyFinal
    | StageItemInputCreateBodyEmpty
)


class StageItemInputUpdateBodyTentative(BaseModelORM):
    winner_from_stage_item_id: StageItemId
    winner_position: int = Field(ge=1)


class StageItemInputUpdateBodyFinal(BaseModelORM):
    team_id: TeamId


class StageItemInputUpdateBodyEmpty(BaseModelORM):
    team_id: None = None
    winner_from_stage_item_id: None = None
    winner_position: None = None


StageItemInputUpdateBody = (
    StageItemInputUpdateBodyTentative
    | StageItemInputUpdateBodyFinal
    | StageItemInputUpdateBodyEmpty
)


class StageItemInputInsertable(ApiModel):
    slot: int
    team_id: TeamId | None = None
    tournament_id: TournamentId
    stage_item_id: StageItemId


class StageItemInputOptionFinal(ApiModel):
    team_id: TeamId
    already_taken: bool


class StageItemInputOptionTentative(ApiModel):
    winner_from_stage_item_id: StageItemId
    winner_position: int
    already_taken: bool


class StageItemInputUpdate(ApiModel):
    """A team that takes a slot when the slot's stage is activated."""

    stage_item_input: StageItemInputTentative
    team: Team
    # A team that is level with `team` on every criterion, but goes elsewhere or doesn't go
    # through: only their seeding decided which of the two takes this slot.
    tied_team: Team | None = None
