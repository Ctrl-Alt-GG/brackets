from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

# Larger than any tournament's players or teams can get (see `bracket.logic.subscriptions`), so the
# frontend can load all of them with one request.
MAX_PAGE_SIZE = 500

# What teams and players can be sorted by.
ParticipantSortField = Literal[
    "name", "elo_score", "swiss_score", "wins", "draws", "losses", "active", "created"
]
# Worked out from the matches on every request, so these sorts happen after loading every row.
RESULT_SORT_FIELDS: frozenset[ParticipantSortField] = frozenset(
    {"elo_score", "swiss_score", "wins", "draws", "losses"}
)


class Pagination(BaseModel):
    """One page of a list. Routes read it from the query string."""

    model_config = ConfigDict(frozen=True)

    limit: int = Field(
        default=25, ge=1, le=MAX_PAGE_SIZE, description="Max number of results in a single page."
    )
    offset: int = Field(default=0, ge=0, description="Filter results starting from this offset.")
    sort_direction: Literal["asc", "desc"] = "asc"


class ParticipantPagination(Pagination):
    sort_by: ParticipantSortField = "name"

    @property
    def sorts_by_results(self) -> bool:
        return self.sort_by in RESULT_SORT_FIELDS
