"""
The rules that cover all events of an account, or all tournaments of an event, hold when two
commands check them at the same time: the second waits for the first and sees what it did.
"""

import asyncio
from collections.abc import AsyncIterator, Awaitable, Callable, Coroutine
from contextlib import asynccontextmanager
from typing import Any

import pytest
from fastapi import HTTPException
from sqlalchemy import Connection, delete, event, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from bracket import orm
from bracket.database import engine, session_scope
from bracket.logic.clubs import create_owned_club, rename_club, transfer_club_ownership
from bracket.logic.subscriptions import LIMITS, Limit
from bracket.logic.tournaments import create_tournament
from bracket.models.db.club import ClubCreateBody, ClubUpdateBody
from bracket.models.db.tournament import TournamentBody
from bracket.models.db.user import UserInDB, UserPublic
from bracket.models.enums import UserAccountType, UserXClubRelation
from bracket.sql.clubs import sql_give_user_access_to_club
from bracket.utils.id_types import ClubId
from tests.dummy_records import DUMMY_MOCK_TIME, DUMMY_USER
from tests.integration_tests.sql import inserted_user

pytestmark = pytest.mark.asyncio(loop_scope="session")

Command = Callable[[], Coroutine[Any, Any, Any]]


def public(user: UserInDB) -> UserPublic:
    return UserPublic.model_validate(user.model_dump(exclude={"password_hash"}))


@asynccontextmanager
async def organizer(name: str) -> AsyncIterator[UserPublic]:
    async with inserted_user(
        DUMMY_USER.model_copy(update={"email": f"{name}@example.org", "name": name})
    ) as user:
        try:
            yield public(user)
        finally:
            async with session_scope() as session:
                clubs = select(orm.UserXClub.club_id).where(orm.UserXClub.user_id == user.id)
                await session.execute(
                    delete(orm.Tournament).where(orm.Tournament.club_id.in_(clubs))
                )
                await session.execute(delete(orm.Club).where(orm.Club.id.in_(clubs)))


async def race(
    first: Callable[[AsyncSession], Awaitable[Any]], second: Command, waits_with: str
) -> Any:
    """
    Run `first` in a transaction and keep it open until `second`, in another one, sends the
    locking statement that contains `waits_with`. Returns what `second` returns or raises.
    """
    holding, release = asyncio.Event(), asyncio.Event()
    second_waits = asyncio.Event()

    async def run_first() -> None:
        async with session_scope() as session:
            await first(session)
            holding.set()
            await release.wait()

    def on_statement(_connection: Connection, _cursor: Any, statement: str, *_args: Any) -> None:
        if waits_with in statement:
            second_waits.set()

    first_task = asyncio.create_task(run_first())
    await holding.wait()
    event.listen(engine.sync_engine, "before_cursor_execute", on_statement)
    try:
        second_task = asyncio.create_task(second())
        await asyncio.wait_for(second_waits.wait(), timeout=2)
    finally:
        event.remove(engine.sync_engine, "before_cursor_execute", on_statement)
    release.set()
    await first_task
    return await second_task


async def refused(command: Awaitable[Any]) -> str:
    with pytest.raises(HTTPException) as exception:
        await command
    return str(exception.value.detail)


async def test_two_events_with_the_same_name() -> None:
    async with organizer("owner") as owner:

        async def create(session: AsyncSession) -> None:
            await create_owned_club(session, ClubCreateBody(name="LAN"), owner)

        async def create_again() -> None:
            async with session_scope() as session:
                await create_owned_club(session, ClubCreateBody(name="lan"), owner)

        assert await refused(race(create, create_again, "NO KEY UPDATE")) == (
            "You already have an event with this name"
        )


async def test_two_renames_to_the_same_name() -> None:
    async with organizer("owner") as owner:
        async with session_scope() as session:
            first = await create_owned_club(session, ClubCreateBody(name="Spring"), owner)
            second = await create_owned_club(session, ClubCreateBody(name="Autumn"), owner)

        async def rename_first(session: AsyncSession) -> None:
            await rename_club(session, first.id, ClubUpdateBody(name="Summer"), owner)

        async def rename_second() -> None:
            async with session_scope() as session:
                await rename_club(session, second.id, ClubUpdateBody(name="summer"), owner)

        assert await refused(race(rename_first, rename_second, "NO KEY UPDATE")) == (
            "You already have an event with this name"
        )


async def test_a_transfer_while_the_new_owner_creates_an_event_with_its_name() -> None:
    async with organizer("owner") as owner, organizer("successor") as successor:
        async with session_scope() as session:
            club = await create_owned_club(session, ClubCreateBody(name="Winter"), owner)
            await sql_give_user_access_to_club(
                session, successor.id, club.id, UserXClubRelation.COLLABORATOR
            )

        async def create(session: AsyncSession) -> None:
            await create_owned_club(session, ClubCreateBody(name="Winter"), successor)

        async def transfer() -> None:
            async with session_scope() as session:
                await transfer_club_ownership(session, club.id, successor.id)

        assert await refused(race(create, transfer, "NO KEY UPDATE")) == (
            "successor already owns an event called Winter. Rename one of them first."
        )


async def test_two_tournaments_for_the_last_place(monkeypatch: pytest.MonkeyPatch) -> None:
    async with organizer("owner") as owner:
        async with session_scope() as session:
            club = await create_owned_club(session, ClubCreateBody(name="Full"), owner)
        monkeypatch.setitem(LIMITS[UserAccountType.REGULAR], Limit.TOURNAMENTS, 1)

        def body(club_id: ClubId, name: str) -> TournamentBody:
            return TournamentBody(
                club_id=club_id,
                name=name,
                start_time=DUMMY_MOCK_TIME,
                dashboard_public=False,
                players_can_be_in_multiple_teams=False,
                duration_minutes=10,
                margin_minutes=5,
            )

        async def create(session: AsyncSession) -> None:
            await create_tournament(session, body(club.id, "First"), owner)

        async def create_another() -> None:
            async with session_scope() as session:
                await create_tournament(session, body(club.id, "Second"), owner)

        assert await refused(race(create, create_another, "NO KEY UPDATE")) == (
            "That would be more than the 1 tournaments in an event that are allowed."
        )
        async with session_scope(read_only=True) as session:
            count = await session.scalar(
                select(func.count())
                .select_from(orm.Tournament)
                .where(orm.Tournament.club_id == club.id)
            )
        assert count == 1
