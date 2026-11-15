from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import Annotated

from fastapi import Depends, Request
from sqlalchemy import make_url
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from bracket.config import config

READ_METHODS = frozenset({"GET", "HEAD", "OPTIONS"})

engine = create_async_engine(
    make_url(str(config.pg_dsn)).set(drivername="postgresql+asyncpg"),
    isolation_level="READ COMMITTED",
)
session_factory = async_sessionmaker(engine, expire_on_commit=False)
read_session_factory = async_sessionmaker(
    engine.execution_options(isolation_level="REPEATABLE READ", postgresql_readonly=True),
    expire_on_commit=False,
)


@asynccontextmanager
async def session_scope(*, read_only: bool = False) -> AsyncIterator[AsyncSession]:
    """One transaction, with a stable snapshot for reads and rollback on failure."""
    factory = read_session_factory if read_only else session_factory
    async with factory() as session, session.begin():
        yield session


async def get_session(request: Request) -> AsyncIterator[AsyncSession]:
    # Function scope finishes the transaction before FastAPI sends the response.
    async with session_scope(read_only=request.method in READ_METHODS) as session:
        yield session


DbSession = Annotated[AsyncSession, Depends(get_session, scope="function")]
