from pydantic import BaseModel

from bracket.logic.ranking.statistics import TeamStatistics
from bracket.models.db.player import Player
from bracket.models.db.ranking import Ranking
from bracket.models.db.team import FullTeamWithPlayers
from bracket.models.db.tournament import Tournament
from bracket.models.db.util import StageWithStageItems
from bracket.utils.id_types import StageItemId, StageItemInputId


class StageItemInputStanding(TeamStatistics):
    stage_item_input_id: StageItemInputId


class TournamentDetails(BaseModel):
    """What the Details pages of a tournament show: one answer instead of six requests."""

    tournament: Tournament
    # Without draft rounds, which only organizers see.
    stages: list[StageWithStageItems]
    players: list[Player]
    teams: list[FullTeamWithPlayers]
    rankings: list[Ranking]
    # The ranked inputs of every stage item by stage item id, best first.
    standings: dict[StageItemId, list[StageItemInputStanding]]


class TournamentAccess(BaseModel):
    can_manage: bool
