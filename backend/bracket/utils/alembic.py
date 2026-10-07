from alembic.config import Config
from sqlalchemy import Connection

from alembic import command
from bracket.utils.logging import logger


def get_alembic_config(connection: Connection) -> Config:
    alembic_config = Config("alembic.ini")
    # Alembic's way to share a connection: env.py migrates on it instead of connecting itself.
    alembic_config.attributes["connection"] = connection
    return alembic_config


def alembic_run_migrations(connection: Connection) -> None:
    logger.info("Running migrations")
    command.upgrade(get_alembic_config(connection), "head")


def alembic_stamp_head(connection: Connection) -> None:
    logger.info("Overwriting current version to be the latest revision (head)")
    command.stamp(get_alembic_config(connection), "head")
