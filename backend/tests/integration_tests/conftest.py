"""
The integration tests run in a database of their own, created on the server `PG_DSN` names and
dropped afterwards. They never create or drop tables in the database `PG_DSN` itself names. Their
uploads go to a temporary directory.

Every test process creates its own, so parallel workers (`pytest -n`) don't share data either.
Both have to exist before the application reads its configuration, which is why this module
imports the application only inside fixtures.
"""

# pylint: disable=redefined-outer-name,import-outside-toplevel
import asyncio
import os
import shutil
import sys
import tempfile
from collections.abc import AsyncIterator
from typing import TYPE_CHECKING
from uuid import uuid4

import asyncpg  # type: ignore[import-untyped]
import pytest
import pytest_asyncio
from sqlalchemy.engine import URL, make_url

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession

    from tests.integration_tests.models import AuthContext


def _admin_dsn(url: URL) -> str:
    return url.set(drivername="postgresql").render_as_string(hide_password=False)


async def _execute(dsn: str, statement: str) -> None:
    connection = await asyncpg.connect(dsn)
    try:
        await connection.execute(statement)
    finally:
        await connection.close()


def pytest_configure(config: pytest.Config) -> None:
    # The controller of parallel workers runs no tests; every worker creates its own database.
    if not hasattr(config, "workerinput") and getattr(config.option, "numprocesses", None):
        return
    if "bracket.config" in sys.modules:
        raise pytest.UsageError(
            "The application was imported before the integration tests created their database"
        )

    configured = make_url(os.environ["PG_DSN"])
    database = f"bracket_test_{uuid4().hex}"
    asyncio.run(_execute(_admin_dsn(configured), f'CREATE DATABASE "{database}"'))
    os.environ["PG_DSN"] = configured.set(database=database).render_as_string(hide_password=False)
    config.add_cleanup(
        lambda: asyncio.run(
            _execute(_admin_dsn(configured), f'DROP DATABASE "{database}" WITH (FORCE)')
        )
    )
    uploads = tempfile.mkdtemp(prefix="bracket-test-uploads-")
    os.environ["UPLOAD_DIR"] = uploads
    config.add_cleanup(lambda: shutil.rmtree(uploads, ignore_errors=True))


@pytest_asyncio.fixture(scope="session", autouse=True, loop_scope="session")
async def database_tables() -> AsyncIterator[None]:
    """The tables, at the latest migration, so the app's startup has nothing left to migrate."""
    from bracket import orm
    from bracket.database import engine
    from bracket.utils.alembic import alembic_stamp_head

    async with engine.begin() as connection:
        await connection.run_sync(orm.Base.metadata.create_all)
        await connection.run_sync(alembic_stamp_head)
    try:
        yield
    finally:
        await engine.dispose()


@pytest_asyncio.fixture(loop_scope="session")
async def session() -> AsyncIterator["AsyncSession"]:
    """Autocommitted ORM writes are immediately visible to requests served by the test API."""
    from sqlalchemy.ext.asyncio import AsyncSession

    from bracket.database import engine

    async with engine.connect() as connection:
        await connection.execution_options(isolation_level="AUTOCOMMIT")
        async with AsyncSession(bind=connection, expire_on_commit=False) as db_session:
            yield db_session


@pytest.fixture(scope="session")
async def auth_context(database_tables: None) -> AsyncIterator["AuthContext"]:
    from tests.dummy_records import DUMMY_TOURNAMENT
    from tests.integration_tests.sql import inserted_auth_context

    async with inserted_auth_context(DUMMY_TOURNAMENT.dashboard_endpoint) as auth_context:
        yield auth_context
