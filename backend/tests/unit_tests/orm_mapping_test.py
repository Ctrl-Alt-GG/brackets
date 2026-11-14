import pytest
from pydantic import TypeAdapter
from sqlalchemy import Enum, create_engine, inspect, select
from sqlalchemy.dialects import postgresql
from sqlalchemy.exc import InvalidRequestError
from sqlalchemy.orm import Session

from bracket import orm
from bracket.models.db.stage_item import StageType
from bracket.models.db.stage_item_inputs import (
    StageItemInput,
    StageItemInputEmpty,
    StageItemInputFinal,
    StageItemInputTentative,
)
from bracket.models.db.util import StageItemWithRounds
from bracket.orm.types import StageTypeEnum
from bracket.utils.dummy_records import DUMMY_MOCK_TIME, DUMMY_TEAM1


@pytest.mark.parametrize(
    ("team_id", "source_id", "position", "expected_type"),
    [
        (None, None, None, StageItemInputEmpty),
        (None, 7, 2, StageItemInputTentative),
        (3, None, None, StageItemInputFinal),
        (3, 7, 2, StageItemInputFinal),
    ],
)
def test_slot_union_from_orm_attributes(
    team_id: int | None,
    source_id: int | None,
    position: int | None,
    expected_type: type[StageItemInput],
) -> None:
    team = (
        orm.Team(**{**DUMMY_TEAM1.model_dump(), "id": team_id, "tournament_id": 1})
        if team_id is not None
        else None
    )
    slot = orm.StageItemInput(
        id=5,
        slot=1,
        tournament_id=1,
        stage_item_id=6,
        team_id=team_id,
        winner_from_stage_item_id=source_id,
        winner_position=position,
        points=0,
        wins=0,
        draws=0,
        losses=0,
        team=team,
    )

    parsed = TypeAdapter(StageItemInput).validate_python(slot)

    assert type(parsed) is expected_type
    assert parsed.team_id == team_id
    assert parsed.winner_from_stage_item_id == source_id
    assert parsed.winner_position == position
    if isinstance(parsed, StageItemInputFinal):
        assert parsed.team.id == team_id
        assert parsed.team.name == DUMMY_TEAM1.name


@pytest.mark.parametrize("stage_type", list(StageType))
def test_stage_item_tree_from_orm_attributes(stage_type: StageType) -> None:
    item = orm.StageItem(
        id=2,
        stage_id=1,
        name="Groups",
        created=DUMMY_MOCK_TIME,
        type=stage_type,
        team_count=4,
        ranking_id=3,
        inputs=[],
        rounds=[],
    )

    parsed = StageItemWithRounds.model_validate(item)

    assert parsed.type is stage_type
    assert parsed.type_name == stage_type.value.lower().capitalize().replace("_", " ")
    assert parsed.inputs == []
    assert parsed.rounds == []


def test_relationships_reject_implicit_loading() -> None:
    engine = create_engine("sqlite://")
    orm.Base.metadata.create_all(engine)
    try:
        with Session(engine) as session:
            session.add(
                orm.Stage(
                    id=1,
                    tournament_id=1,
                    name="Groups",
                    created=DUMMY_MOCK_TIME,
                    is_active=False,
                )
            )
            session.flush()
            session.expunge_all()
            stage = session.scalars(select(orm.Stage)).one()

            with pytest.raises(InvalidRequestError, match="lazy='raise'"):
                _ = stage.stage_items
    finally:
        engine.dispose()

    for mapper in orm.Base.registry.mappers:
        for relationship in mapper.relationships:
            assert relationship.lazy == "raise", (mapper.class_.__name__, relationship.key)


def test_stage_enum_preserves_database_order_and_python_members() -> None:
    dialect = postgresql.dialect()
    column_type = inspect(orm.StageItem).columns.type.type.dialect_impl(dialect)
    assert isinstance(column_type, StageTypeEnum)
    assert isinstance(column_type.impl, Enum)
    assert column_type.impl.enums == ["SINGLE_ELIMINATION", "SWISS", "ROUND_ROBIN"]

    bind = column_type.bind_processor(dialect)
    result = column_type.result_processor(dialect, None)
    assert bind is not None
    assert result is not None
    for stage_type in StageType:
        assert bind(stage_type) == stage_type.value
        assert result(stage_type.value) is stage_type
