from typing import Any

import pytest
from pydantic import ValidationError

from bracket.app import app
from bracket.config import config
from bracket.utils.pagination import MAX_PAGE_SIZE, ParticipantPagination


def test_options_built_in_code_are_ordinary_values() -> None:
    pagination = ParticipantPagination()
    assert (pagination.limit, pagination.offset) == (25, 0)
    assert type(pagination.limit) is int and type(pagination.offset) is int
    assert (pagination.sort_by, pagination.sort_direction) == ("name", "asc")


@pytest.mark.parametrize(
    "options",
    [{"limit": 0}, {"limit": MAX_PAGE_SIZE + 1}, {"offset": -1}, {"sort_by": "email"}],
)
def test_options_are_validated_wherever_they_are_built(options: dict[str, Any]) -> None:
    with pytest.raises(ValidationError):
        ParticipantPagination(**options)


def test_sorting_by_results_is_told_apart_from_stored_fields() -> None:
    assert ParticipantPagination(sort_by="wins").sorts_by_results
    assert not ParticipantPagination(sort_by="created").sorts_by_results


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
