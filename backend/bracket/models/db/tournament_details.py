from bracket.models.db.player import Player
from bracket.models.db.ranking import Ranking
from bracket.models.db.shared import ApiModel
from bracket.models.db.stage_item_inputs import (
    StageItemInputOptionFinal,
    StageItemInputOptionTentative,
    StageItemInputUpdate,
)
from bracket.models.db.stage_tree import StageWithStageItems
from bracket.models.db.team import FullTeamWithPlayers
from bracket.models.db.tournament import Tournament
from bracket.models.results import TeamStatistics
from bracket.utils.id_types import StageId, StageItemId, StageItemInputId


class StageItemInputStanding(TeamStatistics):
    stage_item_input_id: StageItemInputId


class TournamentDetails(ApiModel):
    """What the Details pages of a tournament show: one answer instead of six requests."""

    tournament: Tournament
    # Without draft rounds, which only organizers see.
    stages: list[StageWithStageItems]
    players: list[Player]
    teams: list[FullTeamWithPlayers]
    rankings: list[Ranking]
    # The ranked inputs of every stage item by stage item id, best first.
    standings: dict[StageItemId, list[StageItemInputStanding]]


class TournamentWorkspace(ApiModel):
    """
    What organizers work with, from one database snapshot, so that the stages, the choices for
    their slots, the standings and who would advance all agree.
    """

    tournament: Tournament
    # With the draft rounds.
    stages: list[StageWithStageItems]
    players: list[Player]
    teams: list[FullTeamWithPlayers]
    rankings: list[Ranking]
    standings: dict[StageItemId, list[StageItemInputStanding]]
    # What each stage's slots can take: a team, or a place of an earlier stage item.
    available_inputs: dict[StageId, list[StageItemInputOptionTentative | StageItemInputOptionFinal]]
    # The teams that would take the slots of the next stage if it were activated now.
    next_stage_rankings: dict[StageItemId, list[StageItemInputUpdate]]


class TournamentAccess(ApiModel):
    can_manage: bool
