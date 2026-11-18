"""Results worked out by replaying matches, as the API reports them."""

from decimal import Decimal
from typing import NamedTuple

from bracket.models.db.shared import ApiModel
from bracket.utils.id_types import TeamId

# The rating every team and player starts a tournament with.
START_ELO = Decimal("1200")


class TeamStatistics(ApiModel):
    """The results of a team in one stage item, which rank it there."""

    wins: int = 0
    draws: int = 0
    losses: int = 0
    # What the stage item's ranking awards. In Swiss stage items, the slot's rating instead.
    points: Decimal = Decimal("0.00")
    score_for: int = 0
    score_against: int = 0

    @property
    def score_difference(self) -> int:
        return self.score_for - self.score_against


class ResultTotals(ApiModel):
    """The results of a team or a player over every published match of a tournament."""

    wins: int = 0
    draws: int = 0
    losses: int = 0
    elo_score: Decimal = START_ELO
    # A win counts 1 and a draw 0.5.
    swiss_score: Decimal = Decimal("0.0")


class TeamMatchResult(NamedTuple):
    """A published match with a result, between the two teams that played it."""

    team1_id: TeamId
    team2_id: TeamId
    score1: int
    score2: int
