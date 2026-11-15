from collections.abc import AsyncIterator
from uuid import uuid4

import asyncpg  # type: ignore[import-untyped]
import pytest_asyncio
from sqlalchemy.engine import make_url
from sqlalchemy.ext.asyncio import AsyncEngine, create_async_engine

from bracket.config import config


@pytest_asyncio.fixture
async def migration_engine() -> AsyncIterator[AsyncEngine]:
    """A database isolated from metadata-created integration fixtures."""
    url = make_url(str(config.pg_dsn)).set(drivername="postgresql")
    database = f"bracket_migration_{uuid4().hex}"
    admin = await asyncpg.connect(url.render_as_string(hide_password=False))
    await admin.execute(f'CREATE DATABASE "{database}"')
    engine = create_async_engine(url.set(database=database, drivername="postgresql+asyncpg"))
    try:
        yield engine
    finally:
        await engine.dispose()
        await admin.execute(f'DROP DATABASE "{database}" WITH (FORCE)')
        await admin.close()
