from decimal import Decimal

from pydantic import BaseModel

START_ELO = Decimal("1200")


class TeamStatistics(BaseModel):
    wins: int = 0
    draws: int = 0
    losses: int = 0
    points: Decimal = Decimal("0.00")
    score_for: int = 0
    score_against: int = 0

    @property
    def score_difference(self) -> int:
        return self.score_for - self.score_against


class PlayerStatistics(BaseModel):
    wins: int = 0
    draws: int = 0
    losses: int = 0
    elo_score: Decimal = START_ELO
    swiss_score: Decimal = Decimal("0.0")
