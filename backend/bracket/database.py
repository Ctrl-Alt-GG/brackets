from collections.abc import AsyncIterator
from typing import Annotated

from fastapi import Depends
from sqlalchemy import make_url
from sqlalchemy.ext.asyncio import AsyncConnection, create_async_engine

from bracket.config import config

engine = create_async_engine(make_url(str(config.pg_dsn)).set(drivername="postgresql+asyncpg"))


async def get_connection() -> AsyncIterator[AsyncConnection]:
    async with engine.begin() as connection:
        yield connection


# A request's changes are committed together, before its response is sent, so a client that
# refetches right after a change always sees it.
DbConnection = Annotated[AsyncConnection, Depends(get_connection, scope="function")]
