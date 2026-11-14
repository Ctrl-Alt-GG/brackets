from collections.abc import AsyncIterator
from typing import Annotated

from fastapi import Depends
from sqlalchemy import make_url
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine

from bracket.config import config

engine = create_async_engine(make_url(str(config.pg_dsn)).set(drivername="postgresql+asyncpg"))


async def get_session() -> AsyncIterator[AsyncSession]:
    # The outer transaction commits before FastAPI sends the response, including when a route
    # only flushes its changes. All dependencies in a request share this session and transaction.
    async with engine.begin() as connection:
        async with AsyncSession(bind=connection, expire_on_commit=False) as session:
            yield session
            await session.flush()


DbSession = Annotated[AsyncSession, Depends(get_session, scope="function")]
