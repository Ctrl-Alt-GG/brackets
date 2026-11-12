#!/usr/bin/env python3
import asyncio
import functools
import json
import logging
import os
import subprocess
import sys
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
    get_user,
    update_user_password,
)
from bracket.utils.db_init import sql_create_dev_db
from bracket.utils.rate_limit import get_account_lockout_key, reset_account_failures
from bracket.utils.security import hash_password, normalize_email, validate_password_strength
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
@click.option("--output", type=click.Path(path_type=Path), default=OPENAPI_JSON_PATH)
@click.option("--api-prefix", default="/api", show_default=True)
def generate_openapi(output: Path, api_prefix: str) -> None:
    """Export the frontend's canonical API contract, independently of local server routing."""
    if config.api_prefix != api_prefix:
        # Routes, operation IDs and request-body component names all incorporate the prefix
        # while importing the app. Re-import with that prefix rather than rewriting its schema.
        subprocess.run(
            [
                sys.executable,
                str(Path(__file__).resolve()),
                "generate-openapi",
                "--output",
                str(output),
                "--api-prefix",
                api_prefix,
            ],
            env={**os.environ, "API_PREFIX": api_prefix},
            check=True,
        )
        return
    schema = app.openapi()
    output.write_text(json.dumps(schema, indent=2, sort_keys=True))
    logger.info(f"OpenAPI schema saved to {output}")


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
@click.option(
    "--address",
    prompt="Client address",
    help="The address the failed logins came from, as the reverse proxy logs it.",
)
def clear_user_lock(email: str, address: str) -> None:
    """Lift the lock that repeated failed logins put on an account for one client address."""
    normalized_email = normalize_email(email)
    reset_account_failures(get_account_lockout_key(normalized_email, address=address))
    logger.info(f"Cleared login lock for {normalized_email} from {address}")


@cli.command()
@run_async
async def create_dev_db(conn: AsyncConnection) -> None:
    await sql_create_dev_db(conn)


def checked_password(password: str, email: str, name: str) -> str:
    try:
        return validate_password_strength(password, (email, name))
    except ValueError as exc:
        raise click.ClickException(str(exc)) from exc


@cli.command()
@click.option("--email", prompt="Email", help="The email used to log into the account.")
@click.option(
    "--password",
    prompt="Password",
    hide_input=True,
    confirmation_prompt=True,
    help="The password used to log into the account. Leave it out to be asked for it.",
)
@click.option("--name", prompt="Name", help="The name associated with the account.")
@run_async
async def register_user(conn: AsyncConnection, email: str, password: str, name: str) -> None:
    user = UserInsertable(
        email=email,
        password_hash=hash_password(checked_password(password, email, name)),
        name=name,
        created=datetime_utc.now(),
        account_type=UserAccountType.REGULAR,
    )
    if await check_whether_email_is_in_use(conn, email):
        logger.error("Email address already in use")
        raise SystemExit(1)
    user_created = await create_user(conn, user)
    logger.info(f"Created user with id: {user_created.id}")


@cli.command()
@click.option("--email", prompt="Email", help="The email used to log into the account.")
@click.option(
    "--password",
    prompt="New password",
    hide_input=True,
    confirmation_prompt=True,
    help="The new password. Leave it out to be asked for it.",
)
@run_async
async def set_password(conn: AsyncConnection, email: str, password: str) -> None:
    """
    Give an account a new password, for an organizer who forgot theirs.

    There is no reset by email: the site sends none. Every session of the account ends.
    """
    user = await get_user(conn, email)
    if user is None:
        logger.error("No account has this email address")
        raise SystemExit(1)

    await update_user_password(
        conn, user.id, hash_password(checked_password(password, user.email, user.name))
    )
    logger.info(f"Changed the password of {user.email}")


if __name__ == "__main__":
    cli()
