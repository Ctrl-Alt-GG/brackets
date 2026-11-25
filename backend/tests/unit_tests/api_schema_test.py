"""The API schema says what requests may leave out and what answers always contain."""

import importlib
from typing import Any

import pytest
from pydantic import BaseModel

from bracket.app import app
from bracket.models.db.match import (
    MatchBody,
    MatchCreateBodyFrontend,
    MatchWithDetails,
    MatchWithDetailsDefinitive,
)
from bracket.models.db.participation import TournamentPlayer, TournamentTeamWithPlayers
from bracket.models.db.player import Player
from bracket.models.db.ranking import Ranking, RankingCreateBody
from bracket.models.db.round import RoundCreateBody
from bracket.models.db.stage import StageActivateBody, StageUpdateBody
from bracket.models.db.stage_item import StageItemCreateBody
from bracket.models.db.stage_tree import StageItemWithRounds
from bracket.models.db.team import TeamBody, TeamWithMembers
from bracket.models.db.tournament import Tournament, TournamentBody
from bracket.models.db.user import UserToUpdate


def component(model: type[BaseModel]) -> dict[str, Any]:
    schema: dict[str, Any] = app.openapi()["components"]["schemas"][model.__name__]
    return schema


@pytest.mark.parametrize(
    "model",
    [
        MatchBody,
        MatchCreateBodyFrontend,
        RankingCreateBody,
        RoundCreateBody,
        StageActivateBody,
        StageItemCreateBody,
        StageUpdateBody,
        TeamBody,
        TournamentBody,
        UserToUpdate,
    ],
)
def test_a_request_requires_the_fields_without_defaults(model: type[BaseModel]) -> None:
    required = {name for name, field in model.model_fields.items() if field.is_required()}
    assert set(component(model).get("required", [])) == required


@pytest.mark.parametrize(
    "model",
    [
        MatchWithDetails,
        MatchWithDetailsDefinitive,
        Player,
        Ranking,
        StageItemWithRounds,
        TeamWithMembers,
        Tournament,
        TournamentPlayer,
        TournamentTeamWithPlayers,
    ],
)
def test_an_answer_contains_every_field(model: type[BaseModel]) -> None:
    schema = component(model)
    assert set(schema["required"]) == set(schema["properties"])


def test_exporting_the_schema_changes_no_model() -> None:
    before = StageItemCreateBody.model_json_schema()
    importlib.import_module("cli")
    assert StageItemCreateBody.model_json_schema() == before
    assert "name" not in before.get("required", [])
