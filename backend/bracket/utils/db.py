from typing import Any

from pydantic import BaseModel
from sqlalchemy import Table
from sqlalchemy.ext.asyncio import AsyncConnection
from sqlalchemy.sql import Select

from bracket.config import Environment, environment
from bracket.utils.conversion import to_string_mapping
from bracket.utils.logging import logger
from bracket.utils.types import assert_some


async def fetch_one_parsed[BaseModelT: BaseModel](
    conn: AsyncConnection, model: type[BaseModelT], query: Select[Any]
) -> BaseModelT | None:
    record = (await conn.execute(query)).first()
    return model.model_validate(record._mapping) if record is not None else None


async def fetch_one_parsed_certain[BaseModelT: BaseModel](
    conn: AsyncConnection, model: type[BaseModelT], query: Select[Any]
) -> BaseModelT:
    return assert_some(await fetch_one_parsed(conn, model, query))


async def fetch_all_parsed[BaseModelT: BaseModel](
    conn: AsyncConnection, model: type[BaseModelT], query: Select[Any]
) -> list[BaseModelT]:
    records = (await conn.execute(query)).all()
    return [model.model_validate(record._mapping) for record in records]


async def insert_generic[BaseModelT: BaseModel](
    conn: AsyncConnection, data_model: BaseModelT, table: Table, return_type: type[BaseModelT]
) -> tuple[int, BaseModelT]:
    assert environment is not Environment.PRODUCTION, "Below code can allow SQL injection"
    try:
        statement = table.insert().values(**to_string_mapping(data_model)).returning(table)
        row = (await conn.execute(statement)).one()
        return row.id, return_type.model_validate(row._mapping)
    except Exception:
        logger.exception(f"Could not insert {type(data_model).__name__}")
        raise
