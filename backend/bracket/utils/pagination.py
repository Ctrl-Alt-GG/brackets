from typing import Literal, get_args

from pydantic import BaseModel, ConfigDict, Field

# More than the teams a tournament can have (see `bracket.logic.subscriptions`), so one page holds
# all of them. A lineup can be longer than a page.
MAX_PAGE_SIZE = 500

# Worked out from the matches on every request, so these sorts happen after loading every row.
ResultSortField = Literal["elo_score", "swiss_score", "wins", "draws", "losses"]
RESULT_SORT_FIELDS: frozenset[str] = frozenset(get_args(ResultSortField))


class Pagination(BaseModel):
    """One page of a list. Routes read it from the query string."""

    model_config = ConfigDict(frozen=True)

    limit: int = Field(
        default=25, ge=1, le=MAX_PAGE_SIZE, description="Max number of results in a single page."
    )
    offset: int = Field(default=0, ge=0, description="Filter results starting from this offset.")
    sort_direction: Literal["asc", "desc"] = "asc"


class ParticipantPagination(Pagination):
    """
    A page of a tournament's teams or players, which can be sorted by their results there. The
    subclasses say what else each can be sorted by.
    """

    sort_by: str

    @property
    def sorts_by_results(self) -> bool:
        return self.sort_by in RESULT_SORT_FIELDS


class TeamPagination(ParticipantPagination):
    # `active` is whether the team plays the rounds still to come.
    sort_by: Literal["name", "active", "created", ResultSortField] = "name"


class PlayerPagination(ParticipantPagination):
    sort_by: Literal["name", "created", ResultSortField] = "name"
