# pylint: disable=redefined-outer-name
import os
from collections.abc import AsyncIterator
from time import sleep

import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import AsyncConnection

from bracket.database import engine
from bracket.schema import metadata
from tests.integration_tests.models import AuthContext
from tests.integration_tests.sql import inserted_auth_context


async def recreate_tables() -> None:
    async with engine.begin() as connection:
        await connection.run_sync(metadata.drop_all)
        await connection.run_sync(metadata.create_all)


@pytest_asyncio.fixture(scope="session", autouse=True)
async def reinit_database(worker_id: str) -> AsyncIterator[None]:
    """
    Creates the test database on the first test run in the session.

    When running in parallel, the first test runner (gw0) creates a "lock" file and initializes the
    database. The other runners poll this file and wait until it has been removed by gw0.
    When running tests sequentially, the master worker just creates the test database and that's it.
    """
    if worker_id == "master":
        await recreate_tables()

        try:
            yield
        finally:
            await engine.dispose()

        return

    lock_path = "/tmp/tm_test_lock"

    if worker_id == "gw0":
        try:
            with open(lock_path, mode="w") as file:
                file.write("")

            await recreate_tables()
        finally:
            os.remove(lock_path)
    else:
        for _ in range(50):
            sleep(0.1)
            if not os.path.exists(lock_path):
                break

    try:
        yield
    finally:
        await engine.dispose()


@pytest_asyncio.fixture(loop_scope="session")
async def conn() -> AsyncIterator[AsyncConnection]:
    """A connection that commits every statement, so the API under test sees changes at once."""
    async with engine.connect() as connection:
        yield await connection.execution_options(isolation_level="AUTOCOMMIT")


@pytest.fixture(scope="session")
async def auth_context(reinit_database: None) -> AsyncIterator[AuthContext]:
    async with inserted_auth_context() as auth_context:
        yield auth_context
