from sqlalchemy import Enum
from sqlalchemy.engine import Dialect
from sqlalchemy.types import TypeDecorator

from bracket.models.enums import StageType


class StageTypeEnum(TypeDecorator[StageType]):
    """Map stage types without changing PostgreSQL's existing enum label order."""

    impl = Enum("SINGLE_ELIMINATION", "SWISS", "ROUND_ROBIN", name="stage_type")
    cache_ok = True

    def process_bind_param(self, value: StageType | str | None, dialect: Dialect) -> str | None:
        return value.value if isinstance(value, StageType) else value

    def process_result_value(self, value: str | None, dialect: Dialect) -> StageType | None:
        return StageType(value) if value is not None else None
