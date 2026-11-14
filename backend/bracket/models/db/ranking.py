from decimal import Decimal
from typing import Annotated

from heliclockter import datetime_utc
from pydantic import BaseModel, Field

from bracket.models.db.shared import BaseModelORM
from bracket.utils.id_types import RankingId, TournamentId

# Far beyond any real points rule. The points are stored as floating point numbers, which hold
# values of this size with more decimals than anyone enters.
MAX_RANKING_POINTS = 1000
RankingPoints = Annotated[Decimal, Field(ge=-MAX_RANKING_POINTS, le=MAX_RANKING_POINTS)]


class RankingInsertable(BaseModel):
    tournament_id: TournamentId
    win_points: Decimal
    draw_points: Decimal
    loss_points: Decimal
    add_score_points: bool
    position: int


class Ranking(BaseModelORM, RankingInsertable):
    id: RankingId
    created: datetime_utc


class RankingBody(BaseModel):
    win_points: RankingPoints
    draw_points: RankingPoints
    loss_points: RankingPoints
    add_score_points: bool
    # Where the ranking goes among the tournament's rankings, 0 being the first: the others move
    # to make room. The first one is the default for new stage items.
    position: int = Field(ge=0)


class RankingCreateBody(BaseModel):
    win_points: RankingPoints = Decimal("1.0")
    draw_points: RankingPoints = Decimal("0.5")
    loss_points: RankingPoints = Decimal("0.0")
    add_score_points: bool = False
