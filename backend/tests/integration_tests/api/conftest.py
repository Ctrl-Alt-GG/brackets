# pylint: disable=redefined-outer-name
from collections.abc import AsyncIterator

import pytest_asyncio


@pytest_asyncio.fixture(loop_scope="session", scope="module", autouse=True)
async def startup_and_shutdown_uvicorn_server() -> AsyncIterator[None]:
    """
    Start server as test fixture and tear down after test
    """
    # Imported here: the integration tests create their database before the app reads its
    # configuration (see `tests/integration_tests/conftest.py`).
    from tests.integration_tests.api.shared import (  # pylint: disable=import-outside-toplevel
        UvicornTestServer,
    )

    server = UvicornTestServer()
    try:
        await server.up()
        yield
    finally:
        await server.down()
