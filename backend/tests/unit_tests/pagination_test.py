from typing import Any

import pytest
from pydantic import ValidationError

from bracket.app import app
from bracket.config import config
from bracket.utils.pagination import MAX_PAGE_SIZE, PlayerPagination, TeamPagination

PaginationType = type[TeamPagination] | type[PlayerPagination]
PAGINATIONS: list[PaginationType] = [TeamPagination, PlayerPagination]


@pytest.mark.parametrize("pagination_type", PAGINATIONS)
def test_options_built_in_code_are_ordinary_values(
    pagination_type: PaginationType,
) -> None:
    pagination = pagination_type()
    assert (pagination.limit, pagination.offset) == (25, 0)
    assert type(pagination.limit) is int and type(pagination.offset) is int
    assert (pagination.sort_by, pagination.sort_direction) == ("name", "asc")


@pytest.mark.parametrize("pagination_type", PAGINATIONS)
@pytest.mark.parametrize(
    "options",
    [{"limit": 0}, {"limit": MAX_PAGE_SIZE + 1}, {"offset": -1}, {"sort_by": "email"}],
)
def test_options_are_validated_wherever_they_are_built(
    pagination_type: PaginationType, options: dict[str, Any]
) -> None:
    with pytest.raises(ValidationError):
        pagination_type(**options)


def test_only_teams_are_active_in_a_tournament() -> None:
    assert TeamPagination(sort_by="active").sort_by == "active"
    with pytest.raises(ValidationError):
        PlayerPagination.model_validate({"sort_by": "active"})


@pytest.mark.parametrize("pagination_type", PAGINATIONS)
def test_sorting_by_results_is_told_apart_from_stored_fields(
    pagination_type: PaginationType,
) -> None:
    assert pagination_type(sort_by="wins").sorts_by_results
    assert not pagination_type(sort_by="created").sorts_by_results


@pytest.mark.parametrize("participants", ["teams", "players"])
def test_the_query_parameters_are_documented(participants: str) -> None:
    operation = app.openapi()["paths"][
        f"{config.api_prefix}/tournaments/{{tournament_id}}/{participants}"
    ]["get"]
    parameters = {parameter["name"]: parameter for parameter in operation["parameters"]}
    assert parameters["limit"]["schema"]["default"] == 25
    assert parameters["limit"]["schema"]["maximum"] == MAX_PAGE_SIZE
    assert parameters["limit"]["description"] == "Max number of results in a single page."
    assert parameters["offset"]["schema"]["minimum"] == 0
    assert "wins" in parameters["sort_by"]["schema"]["enum"]
