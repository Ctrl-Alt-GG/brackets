import asyncio
import logging
import os
import sys

# ruff: noqa: E402 We first need to insert the path
from sqlalchemy import Connection, pool
from sqlalchemy.ext.asyncio import create_async_engine

from alembic import context

parent_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, parent_dir)

from bracket.database import engine
from bracket.schema import metadata

ALEMBIC_CONFIG = context.config
logger = logging.getLogger("alembic")


def run_migrations_offline() -> None:
    url = ALEMBIC_CONFIG.get_main_option("sqlalchemy.url")
    context.configure(url=url, target_metadata=metadata, compare_type=True)

    with context.begin_transaction():
        context.run_migrations()


def do_run_migrations(connection: Connection) -> None:
    context.configure(connection=connection, target_metadata=metadata, compare_type=True)

    with context.begin_transaction():
        context.run_migrations()


async def run_async_migrations() -> None:
    connectable = create_async_engine(engine.url, poolclass=pool.NullPool)

    async with connectable.connect() as connection:
        await connection.run_sync(do_run_migrations)

    await connectable.dispose()


def run_migrations_online() -> None:
    # The app migrates on its own connection (see `bracket.utils.alembic`), the CLI connects here.
    connection = ALEMBIC_CONFIG.attributes.get("connection")
    if connection is not None:
        do_run_migrations(connection)
    else:
        asyncio.run(run_async_migrations())


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
