from dataclasses import dataclass
from typing import Literal

from fastapi import Query

# Larger than any tournament's players or teams can get (see `bracket.logic.subscriptions`), so the
# frontend can load all of them with one request.
MAX_PAGE_SIZE = 500


@dataclass
class Pagination:
    limit: int = Query(
        25, ge=1, le=MAX_PAGE_SIZE, description="Max number of results in a single page."
    )
    offset: int = Query(0, ge=0, description="Filter results starting from this offset.")
    sort_direction: Literal["asc", "desc"] = "asc"


@dataclass
class PaginationPlayers(Pagination):
    sort_by: Literal[
        "name", "elo_score", "swiss_score", "wins", "draws", "losses", "active", "created"
    ] = "name"


@dataclass
class PaginationTeams(Pagination):
    sort_by: Literal[
        "name", "elo_score", "swiss_score", "wins", "draws", "losses", "active", "created"
    ] = "name"
