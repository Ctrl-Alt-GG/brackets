#!/usr/bin/env python3
import asyncio
import functools
import json
import logging
from pathlib import Path
from typing import Any

import click
from heliclockter import datetime_utc
from sqlalchemy.ext.asyncio import AsyncConnection

from bracket.app import app
from bracket.config import config
from bracket.database import engine
from bracket.models.db.account import UserAccountType
from bracket.models.db.user import UserInsertable
from bracket.sql.users import (
    check_whether_email_is_in_use,
    create_user,
)
from bracket.utils.db_init import sql_create_dev_db
from bracket.utils.rate_limit import reset_account_failures
from bracket.utils.security import hash_password, normalize_email
from openapi import openapi  # noqa: F401

OPENAPI_JSON_PATH = "openapi/openapi.json"

logging.basicConfig(format="%(asctime)s [%(name)s] %(levelname)s: %(message)s", level=logging.INFO)
logger = logging.getLogger("cli")


def run_async(f: Any) -> Any:
    """Run an async command in one transaction, which it receives as its first argument."""

    @functools.wraps(f)
    def wrapper(*args: Any, **kwargs: Any) -> Any:
        async def inner() -> None:
            try:
                async with engine.begin() as conn:
                    await f(conn, *args, **kwargs)
            finally:
                await engine.dispose()

        return asyncio.run(inner())

    return wrapper


@click.group()
def cli() -> None:
    pass


@cli.command()
def generate_openapi() -> None:
    schema = app.openapi()
    Path("openapi/openapi.json").write_text(json.dumps(schema, indent=2, sort_keys=True))
    logger.info(f"OpenAPI schema saved to {OPENAPI_JSON_PATH}")


@cli.command()
def hash_password_cmd() -> None:
    if config.admin_password is None:
        logger.error("No admin password is given")
    else:
        hashed_pwd = hash_password(config.admin_password)
        logger.info("Hashed password:")
        logger.info(hashed_pwd)


@cli.command()
@click.option("--email", prompt="Email", help="The email used to log into the account.")
def clear_user_lock(email: str) -> None:
    normalized_email = normalize_email(email)
    reset_account_failures(normalized_email)
    logger.info(f"Cleared login lock for {normalized_email}")


@cli.command()
@run_async
async def create_dev_db(conn: AsyncConnection) -> None:
    await sql_create_dev_db(conn)


@cli.command()
@click.option("--email", prompt="Email", help="The email used to log into the account.")
@click.option("--password", prompt="Password", help="The password used to log into the account.")
@click.option("--name", prompt="Name", help="The name associated with the account.")
@run_async
async def register_user(conn: AsyncConnection, email: str, password: str, name: str) -> None:
    user = UserInsertable(
        email=email,
        password_hash=hash_password(password),
        name=name,
        created=datetime_utc.now(),
        account_type=UserAccountType.REGULAR,
    )
    if await check_whether_email_is_in_use(conn, email):
        logger.error("Email address already in use")
        raise SystemExit(1)
    user_created = await create_user(conn, user)
    logger.info(f"Created user with id: {user_created.id}")


if __name__ == "__main__":
    cli()
