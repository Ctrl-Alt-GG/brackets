"""
When someone loses access to an event, while their commands on its tournaments are in progress.

A command that was let in finishes first, and the removal waits for it. A command that waits for
the removal sees the event's organizers as they are after it, and is refused.
"""

import asyncio
from collections.abc import AsyncIterator, Callable
from contextlib import asynccontextmanager
from typing import Any

import pytest
from fastapi import HTTPException, Response
from sqlalchemy import Connection, event, select
from sqlalchemy.ext.asyncio import AsyncSession
from starlette.requests import Request

from bracket import orm
from bracket.database import engine, session_scope
from bracket.logic.authentication import Credentials
from bracket.logic.tournaments import create_tournament
from bracket.models.db.tournament import TournamentBody
from bracket.models.db.user import UserInDB
from bracket.models.enums import UserXClubRelation
from bracket.routes import access
from bracket.sql.clubs import sql_give_user_access_to_club, sql_remove_user_from_club
from bracket.utils.id_types import TournamentId
from tests.dummy_records import DUMMY_MOCK_TIME, DUMMY_USER
from tests.integration_tests.mocks import get_mock_token
from tests.integration_tests.models import AuthContext
from tests.integration_tests.sql import inserted_auth_context, inserted_user

pytestmark = pytest.mark.asyncio(loop_scope="session")

COMMAND = Request({"type": "http", "method": "PUT"})


@asynccontextmanager
async def collaborator_of(context: AuthContext) -> AsyncIterator[UserInDB]:
    async with inserted_user(
        DUMMY_USER.model_copy(update={"email": "helper@example.org", "name": "Helper"})
    ) as helper:
        async with session_scope() as session:
            await sql_give_user_access_to_club(
                session, helper.id, context.club.id, UserXClubRelation.COLLABORATOR
            )
        yield helper


@asynccontextmanager
async def statement_seen(matches: Callable[[str], bool]) -> AsyncIterator[asyncio.Event]:
    """Set when a statement for which `matches` is true is sent to the database."""
    seen = asyncio.Event()

    def on_statement(_connection: Connection, _cursor: Any, statement: str, *_args: Any) -> None:
        if matches(statement):
            seen.set()

    event.listen(engine.sync_engine, "before_cursor_execute", on_statement)
    try:
        yield seen
    finally:
        event.remove(engine.sync_engine, "before_cursor_execute", on_statement)


def locks(table: str, strength: str) -> Callable[[str], bool]:
    return lambda statement: f"FOR {strength}" in statement and table in statement


async def authorize_command(
    session: AsyncSession, user: UserInDB, tournament_id: TournamentId
) -> None:
    authenticated = await access.user_authenticated(
        session, Response(), Credentials(get_mock_token(user), from_cookie=False)
    )
    await access.user_authenticated_for_tournament(tournament_id, session, COMMAND, authenticated)


async def test_a_command_that_was_let_in_finishes_before_its_user_loses_access() -> None:
    async with inserted_auth_context() as context, collaborator_of(context) as helper:
        tournament_locked, release_tournament = asyncio.Event(), asyncio.Event()
        order: list[str] = []

        async def long_edit() -> None:
            async with session_scope() as session:
                await session.execute(
                    select(orm.Tournament.id)
                    .where(orm.Tournament.id == context.tournament.id)
                    .with_for_update()
                )
                tournament_locked.set()
                await release_tournament.wait()

        async def command() -> None:
            async with session_scope() as session:
                await authorize_command(session, helper, context.tournament.id)
                order.append("command authorized")
            order.append("command committed")

        async def removal() -> None:
            async with session_scope() as session:
                await sql_remove_user_from_club(session, helper.id, context.club.id)
            order.append("access removed")

        edit = asyncio.create_task(long_edit())
        await tournament_locked.wait()
        async with statement_seen(locks("tournaments", "UPDATE")) as command_waits:
            waiting_command = asyncio.create_task(command())
            await asyncio.wait_for(command_waits.wait(), timeout=2)
        async with statement_seen(locks("clubs", "UPDATE")) as removal_waits:
            waiting_removal = asyncio.create_task(removal())
            await asyncio.wait_for(removal_waits.wait(), timeout=2)
        # The removal can't start while the command holds the event.
        await asyncio.sleep(0.2)
        assert order == []

        release_tournament.set()
        await asyncio.gather(edit, waiting_command, waiting_removal)
        assert order == ["command authorized", "command committed", "access removed"]


async def test_a_command_that_waits_for_the_removal_is_refused() -> None:
    async with inserted_auth_context() as context, collaborator_of(context) as helper:
        removing, finish_removal = asyncio.Event(), asyncio.Event()

        async def removal() -> None:
            async with session_scope() as session:
                await sql_remove_user_from_club(session, helper.id, context.club.id)
                removing.set()
                await finish_removal.wait()

        async def command() -> None:
            async with session_scope() as session:
                await authorize_command(session, helper, context.tournament.id)

        waiting_removal = asyncio.create_task(removal())
        await removing.wait()
        async with statement_seen(locks("clubs", "KEY SHARE")) as command_waits:
            waiting_command = asyncio.create_task(command())
            await asyncio.wait_for(command_waits.wait(), timeout=2)
        finish_removal.set()
        await waiting_removal

        with pytest.raises(HTTPException) as refused:
            await waiting_command
        assert refused.value.status_code == 403


async def test_a_tournament_created_while_access_ends_is_refused() -> None:
    async with inserted_auth_context() as context, collaborator_of(context) as helper:
        removing, finish_removal = asyncio.Event(), asyncio.Event()

        async def removal() -> None:
            async with session_scope() as session:
                await sql_remove_user_from_club(session, helper.id, context.club.id)
                removing.set()
                await finish_removal.wait()

        async def creation() -> None:
            async with session_scope() as session:
                user = await access.user_authenticated(
                    session, Response(), Credentials(get_mock_token(helper), from_cookie=False)
                )
                await create_tournament(
                    session,
                    TournamentBody(
                        club_id=context.club.id,
                        name="Too late",
                        start_time=DUMMY_MOCK_TIME,
                        dashboard_public=False,
                        players_can_be_in_multiple_teams=False,
                        duration_minutes=10,
                        margin_minutes=5,
                    ),
                    user,
                )

        waiting_removal = asyncio.create_task(removal())
        await removing.wait()
        async with statement_seen(locks("clubs", "NO KEY UPDATE")) as creation_waits:
            waiting_creation = asyncio.create_task(creation())
            await asyncio.wait_for(creation_waits.wait(), timeout=2)
        finish_removal.set()
        await waiting_removal

        with pytest.raises(HTTPException) as refused:
            await waiting_creation
        assert refused.value.status_code == 403
