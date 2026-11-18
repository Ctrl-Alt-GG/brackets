"""Setting up an empty database, which every worker checks for when it starts."""

from heliclockter import datetime_utc
from sqlalchemy import inspect
from sqlalchemy.ext.asyncio import AsyncConnection, AsyncSession

from bracket import orm
from bracket.config import Environment, config, environment
from bracket.models.db.user import UserInsertable
from bracket.models.enums import UserAccountType
from bracket.sql.users import create_user, get_user
from bracket.utils.alembic import alembic_stamp_head
from bracket.utils.id_types import UserId
from bracket.utils.logging import logger
from bracket.utils.security import hash_password


async def create_admin_user(session: AsyncSession) -> UserId:
    if not (config.admin_email and config.admin_password):
        raise ValueError("Creating an admin requires ADMIN_EMAIL and ADMIN_PASSWORD")

    user = await create_user(
        session,
        UserInsertable(
            name="Admin",
            email=config.admin_email,
            password_hash=hash_password(config.admin_password),
            created=datetime_utc.now(),
            account_type=UserAccountType.REGULAR,
        ),
    )
    return user.id


async def init_db_when_empty(connection: AsyncConnection) -> UserId | None:
    """
    Create the tables in an empty database, and the configured administrator when it has none.
    Returns the administrator's id when it was created.
    """
    table_names = set(await connection.run_sync(lambda sync: inspect(sync).get_table_names()))
    empty = table_names <= {"alembic_version"}
    if not empty and len(table_names) == 1:
        raise RuntimeError("Refusing to initialize a database with an unexpected partial schema")
    if empty:
        logger.warning("Empty db detected, creating tables...")
        await connection.run_sync(orm.Base.metadata.create_all)
        await connection.run_sync(alembic_stamp_head)

    if not (config.admin_email and config.admin_password):
        return None

    async with AsyncSession(bind=connection, expire_on_commit=False) as session:
        if empty or (
            environment is Environment.DEVELOPMENT
            and await get_user(session, config.admin_email) is None
        ):
            logger.warning("Admin user missing, creating admin user...")
            user_id = await create_admin_user(session)
            await session.flush()
            return user_id

    return None
