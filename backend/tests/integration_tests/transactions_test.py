import asyncio
from typing import Any
from uuid import uuid4

import aiohttp
import pytest
from fastapi import FastAPI, HTTPException, Response
from sqlalchemy import Connection, delete, event, func, inspect, select, update
from sqlalchemy.exc import DBAPIError
from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from starlette.requests import Request

from bracket import database, orm
from bracket.bootstrap import init_db_when_empty
from bracket.config import config
from bracket.database import DbSession, engine, session_scope
from bracket.development_seed import create_dev_db
from bracket.logic.authentication import Credentials
from bracket.logic.clubs import remove_club_member, transfer_club_ownership
from bracket.models.db.user import UserPublic
from bracket.models.enums import UserXClubRelation
from bracket.routes import access, tournaments
from bracket.sql.clubs import get_club_members, sql_give_user_access_to_club
from tests.dummy_records import DUMMY_USER
from tests.integration_tests.api.shared import UvicornTestServer, find_free_port
from tests.integration_tests.mocks import get_mock_token
from tests.integration_tests.sql import inserted_auth_context, inserted_user, isolated_schema

pytestmark = pytest.mark.asyncio(loop_scope="session")


async def test_read_transaction_has_one_snapshot_and_refuses_writes() -> None:
    async with session_scope() as session:
        club = orm.Club(name="Before")
        session.add(club)
        await session.flush()
        club_id = club.id

    try:
        async with session_scope(read_only=True) as reader:
            query = select(orm.Club.name).where(orm.Club.id == club_id)
            assert await reader.scalar(query) == "Before"
            assert await reader.scalar(func.current_setting("transaction_isolation")) == (
                "repeatable read"
            )
            assert await reader.scalar(func.current_setting("transaction_read_only")) == "on"
            async with session_scope() as writer:
                assert await writer.scalar(func.current_setting("transaction_isolation")) == (
                    "read committed"
                )
                await writer.execute(
                    update(orm.Club).where(orm.Club.id == club_id).values(name="After")
                )
            assert await reader.scalar(query) == "Before"

        async with session_scope(read_only=True) as reader:
            assert await reader.scalar(query) == "After"

        with pytest.raises(DBAPIError, match="read-only transaction"):
            async with session_scope(read_only=True) as reader:
                reader.add(orm.Club(name="Forbidden write"))
                await reader.flush()
    finally:
        async with session_scope() as session:
            await session.execute(delete(orm.Club).where(orm.Club.id == club_id))


async def test_command_failure_rolls_back_flushed_changes() -> None:
    name = f"Rollback {uuid4().hex}"
    with pytest.raises(ValueError, match="Cancel changes"):
        async with session_scope() as session:
            session.add(orm.Club(name=name))
            await session.flush()
            raise ValueError("Cancel changes")

    async with session_scope(read_only=True) as reader:
        assert await reader.scalar(select(orm.Club.id).where(orm.Club.name == name)) is None


async def test_request_commits_pending_changes_before_sending_response() -> None:
    name = f"Committed {uuid4().hex}"
    app = FastAPI()

    @app.post("/write")
    async def write(session: DbSession) -> dict[str, str]:
        session.add(orm.Club(name=name))
        return {"status": "saved"}

    port = find_free_port()
    server = UvicornTestServer(app, port=port)
    try:
        await server.up()
        async with aiohttp.ClientSession() as client:
            async with client.post(f"http://127.0.0.1:{port}/write") as response:
                assert response.status == 200
                assert await response.json() == {"status": "saved"}
        async with session_scope(read_only=True) as reader:
            assert await reader.scalar(select(orm.Club.id).where(orm.Club.name == name)) is not None
    finally:
        await server.down()
        async with session_scope() as session:
            await session.execute(delete(orm.Club).where(orm.Club.name == name))


async def test_get_request_keeps_snapshot_across_concurrent_commit() -> None:
    async with session_scope() as session:
        club = orm.Club(name="Before request")
        session.add(club)
        await session.flush()
        club_id = club.id
    first_read, writer_committed = asyncio.Event(), asyncio.Event()
    app = FastAPI()

    @app.get("/snapshot")
    async def snapshot(session: DbSession) -> dict[str, str | None]:
        query = select(orm.Club.name).where(orm.Club.id == club_id)
        before = await session.scalar(query)
        first_read.set()
        await writer_committed.wait()
        return {"before": before, "after": await session.scalar(query)}

    port = find_free_port()
    server = UvicornTestServer(app, port=port)
    try:
        await server.up()
        async with aiohttp.ClientSession() as client:

            async def load() -> None:
                async with client.get(f"http://127.0.0.1:{port}/snapshot") as response:
                    assert response.status == 200
                    assert await response.json() == {
                        "before": "Before request",
                        "after": "Before request",
                    }

            request = asyncio.create_task(load())
            try:
                await asyncio.wait_for(first_read.wait(), timeout=2)
                async with session_scope() as writer:
                    await writer.execute(
                        update(orm.Club).where(orm.Club.id == club_id).values(name="After request")
                    )
                writer_committed.set()
                await request
            finally:
                writer_committed.set()
                await asyncio.gather(request, return_exceptions=True)
    finally:
        await server.down()
        async with session_scope() as session:
            await session.execute(delete(orm.Club).where(orm.Club.id == club_id))


async def test_cached_details_release_authorization_connection(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    small_engine = create_async_engine(
        engine.url, pool_size=1, max_overflow=0, pool_timeout=0.5, isolation_level="READ COMMITTED"
    )
    monkeypatch.setattr(
        database, "session_factory", async_sessionmaker(small_engine, expire_on_commit=False)
    )
    monkeypatch.setattr(
        database,
        "read_session_factory",
        async_sessionmaker(
            small_engine.execution_options(
                isolation_level="REPEATABLE READ", postgresql_readonly=True
            ),
            expire_on_commit=False,
        ),
    )
    app = FastAPI()
    app.include_router(tournaments.router)
    port = find_free_port()
    server = UvicornTestServer(app, port=port)
    try:
        async with inserted_auth_context() as context:
            await server.up()
            url = (
                f"http://127.0.0.1:{port}{config.api_prefix}"
                f"/tournaments/{context.tournament.id}/details"
            )

            async def load(client: aiohttp.ClientSession) -> None:
                async with client.get(url, headers=context.headers) as response:
                    assert response.status == 200, await response.text()
                    assert (await response.json())["data"]["tournament"]["id"] == (
                        context.tournament.id
                    )

            try:
                async with aiohttp.ClientSession() as client:
                    await asyncio.gather(*(load(client) for _ in range(3)))
            finally:
                tournaments.get_tournament_details_json.cache_invalidate(context.tournament.id)
    finally:
        await server.down()
        await small_engine.dispose()


@pytest.mark.parametrize("second_action", ["transfer", "leave"])
async def test_membership_changes_recheck_permissions_after_waiting_for_club_lock(
    second_action: str,
) -> None:
    async with (
        inserted_auth_context() as context,
        inserted_user(
            DUMMY_USER.model_copy(update={"email": "successor@example.org", "name": "Successor"})
        ) as successor,
        inserted_user(
            DUMMY_USER.model_copy(update={"email": "another@example.org", "name": "Another"})
        ) as another,
    ):
        async with session_scope() as session:
            for user in (successor, another):
                await sql_give_user_access_to_club(
                    session, user.id, context.club.id, UserXClubRelation.COLLABORATOR
                )
        lock_held, finish_transfer, lock_attempted = (
            asyncio.Event(),
            asyncio.Event(),
            asyncio.Event(),
        )
        request = Request({"type": "http", "method": "PUT"})
        owner_credentials = Credentials(get_mock_token(context.user), from_cookie=False)

        async def authorize(session: AsyncSession, credentials: Credentials) -> UserPublic:
            user = await access.user_authenticated(session, Response(), credentials)
            return await access.user_authenticated_for_club(context.club.id, session, request, user)

        async def transfer() -> None:
            async with session_scope() as session:
                owner = await authorize(session, owner_credentials)
                await access.user_owns_club(context.club.id, session, owner)
                lock_held.set()
                await finish_transfer.wait()
                await transfer_club_ownership(session, context.club.id, successor.id)

        def on_statement(
            _connection: Connection,
            _cursor: Any,
            statement: str,
            _parameters: Any,
            _context: Any,
            _executemany: bool,
        ) -> None:
            if "FOR UPDATE" in statement and "clubs" in statement:
                lock_attempted.set()

        async def competing_change() -> None:
            async with session_scope() as session:
                credentials = (
                    owner_credentials
                    if second_action == "transfer"
                    else Credentials(get_mock_token(successor), from_cookie=False)
                )
                user = await authorize(session, credentials)
                if second_action == "transfer":
                    await access.user_owns_club(context.club.id, session, user)
                    await transfer_club_ownership(session, context.club.id, another.id)
                else:
                    await remove_club_member(session, context.club.id, successor.id, user)

        first = asyncio.create_task(transfer())
        await asyncio.wait_for(lock_held.wait(), timeout=2)
        event.listen(engine.sync_engine, "before_cursor_execute", on_statement)
        second = asyncio.create_task(competing_change())
        try:
            await asyncio.wait_for(lock_attempted.wait(), timeout=2)
            finish_transfer.set()
            await first
            with pytest.raises(HTTPException) as rejected:
                await second
            assert rejected.value.detail == (
                "Only the owner of this event can do that"
                if second_action == "transfer"
                else "The owner can't be removed from the event. Delete the event instead."
            )
        finally:
            finish_transfer.set()
            await asyncio.gather(first, second, return_exceptions=True)
            event.remove(engine.sync_engine, "before_cursor_execute", on_statement)

        async with session_scope(read_only=True) as session:
            owners = [
                member.user_id
                for member in await get_club_members(session, context.club.id)
                if member.relation is UserXClubRelation.OWNER
            ]
            assert owners == [successor.id]


async def test_bootstrap_refuses_partial_database() -> None:
    async with isolated_schema() as isolated:
        async with isolated.begin() as connection:
            await connection.run_sync(orm.Base.metadata.tables["users"].create)
        async with isolated.begin() as connection:
            with pytest.raises(RuntimeError, match="unexpected partial schema"):
                await init_db_when_empty(connection)
            assert await connection.run_sync(lambda c: inspect(c).get_table_names()) == ["users"]


async def test_bootstrap_initializes_empty_database(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(config, "admin_email", None)
    monkeypatch.setattr(config, "admin_password", None)
    async with isolated_schema() as isolated:
        async with isolated.begin() as connection:
            assert await init_db_when_empty(connection) is None
            tables = await connection.run_sync(lambda c: inspect(c).get_table_names())
            assert set(tables) == {*orm.Base.metadata.tables, "alembic_version"}


@pytest.mark.parametrize("admin_email", ["configured@example.org", DUMMY_USER.email])
async def test_development_seed_preserves_one_configured_owner(
    monkeypatch: pytest.MonkeyPatch, admin_email: str
) -> None:
    monkeypatch.setattr(config, "admin_email", admin_email)
    monkeypatch.setattr(config, "admin_password", "A configured administrator passphrase 42!")
    async with isolated_schema() as isolated:
        factory = async_sessionmaker(isolated, expire_on_commit=False)
        async with factory() as session, session.begin():
            dummy_id = await create_dev_db(session)
            members = (
                await session.execute(
                    select(orm.User.email, orm.UserXClub.relation).join(
                        orm.UserXClub, orm.UserXClub.user_id == orm.User.id
                    )
                )
            ).all()
            assert [
                email for email, relation in members if relation is UserXClubRelation.OWNER
            ] == [admin_email]
            dummy_membership = await session.scalar(
                select(orm.UserXClub.relation).where(orm.UserXClub.user_id == dummy_id)
            )
            assert dummy_membership is (
                UserXClubRelation.OWNER
                if admin_email == DUMMY_USER.email
                else UserXClubRelation.COLLABORATOR
            )
            assert await session.scalar(select(func.count()).select_from(orm.Team)) == 8
            assert await session.scalar(select(func.count()).select_from(orm.PlayerXTeam)) == 16
