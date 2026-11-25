"""A logo stored for a command stays only if the command's transaction commits."""

import asyncio
from collections.abc import AsyncIterator, Awaitable, Callable
from io import BytesIO
from pathlib import Path
from typing import Any

import aiofiles
import pytest
import pytest_asyncio
from fastapi import UploadFile
from sqlalchemy.ext.asyncio import AsyncSessionTransaction
from sqlalchemy.orm import SessionTransaction

from bracket import database
from bracket.database import session_scope
from bracket.models.db.team import Team
from bracket.sql.teams import get_team, sql_update_team_logo
from bracket.utils.uploads import (
    StoredUpload,
    UploadFolder,
    build_upload_path,
    store_validated_image_upload,
)
from tests.dummy_records import DUMMY_TEAM1
from tests.integration_tests.sql import inserted_team

pytestmark = pytest.mark.asyncio(loop_scope="session")

LOGO = Path("tests/integration_tests/assets/test_logo.png").read_bytes()


@pytest_asyncio.fixture(loop_scope="session")
async def team() -> AsyncIterator[Team]:
    async with inserted_team(DUMMY_TEAM1) as inserted:
        yield inserted


def replace_next_commit(
    monkeypatch: pytest.MonkeyPatch, commit: Callable[[Callable[[], None]], None]
) -> None:
    """Run `commit` for the next transaction, with that transaction's real commit."""
    original = SessionTransaction.commit
    replaced: list[SessionTransaction] = []

    def next_commit(self: SessionTransaction, _to_root: bool = False) -> None:
        if replaced:
            original(self, _to_root)
            return
        replaced.append(self)
        commit(lambda: original(self, _to_root))

    monkeypatch.setattr(SessionTransaction, "commit", next_commit)


def team_logos() -> set[str]:
    folder = build_upload_path(UploadFolder.TEAM_LOGOS, "")
    return {path.name for path in folder.iterdir()} if folder.exists() else set()


async def replace_logo(
    team: Team, before_commit: Callable[[], Awaitable[None]] | None = None
) -> str:
    """Store a new logo for the team in one transaction, and return its filename."""
    upload: StoredUpload | None = None
    async with session_scope() as session:
        upload = await store_validated_image_upload(
            UploadFile(BytesIO(LOGO), filename="logo.png"), UploadFolder.TEAM_LOGOS, session
        )
        await sql_update_team_logo(session, team.id, upload.filename)
        if before_commit is not None:
            await before_commit()
    return upload.filename


async def logo_of(team: Team) -> str | None:
    async with session_scope(read_only=True) as session:
        loaded = await get_team(session, team.id)
    assert loaded is not None
    return loaded.logo_path


async def test_a_committed_logo_stays(team: Team) -> None:
    filename = await replace_logo(team)
    assert filename in team_logos()
    assert await logo_of(team) == filename
    build_upload_path(UploadFolder.TEAM_LOGOS, filename).unlink()


async def test_a_failed_command_removes_its_new_logo(team: Team) -> None:
    before = team_logos()

    async def fail() -> None:
        raise RuntimeError("the database update failed")

    with pytest.raises(RuntimeError, match="the database update failed"):
        await replace_logo(team, fail)

    assert team_logos() == before
    assert await logo_of(team) is None


async def test_a_failed_commit_removes_the_new_logo(
    team: Team, monkeypatch: pytest.MonkeyPatch
) -> None:
    before = team_logos()

    def refuse(_: Callable[[], None]) -> None:
        raise RuntimeError("the commit failed")

    replace_next_commit(monkeypatch, refuse)
    with pytest.raises(RuntimeError, match="the commit failed"):
        await replace_logo(team)

    assert team_logos() == before
    assert await logo_of(team) is None


async def test_cancellation_after_the_commit_keeps_the_new_logo(
    team: Team, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The commit's outcome is unknown to the request, so the database decides."""
    commit = AsyncSessionTransaction.__aexit__
    cancelled: list[AsyncSessionTransaction] = []

    async def commit_then_cancel(self: AsyncSessionTransaction, *exception: Any) -> None:
        await commit(self, *exception)
        if not cancelled:
            cancelled.append(self)
            raise asyncio.CancelledError

    before = team_logos()
    monkeypatch.setattr(AsyncSessionTransaction, "__aexit__", commit_then_cancel)
    with pytest.raises(asyncio.CancelledError):
        await replace_logo(team)

    [filename] = team_logos() - before
    assert await logo_of(team) == filename
    build_upload_path(UploadFolder.TEAM_LOGOS, filename).unlink()


async def test_new_logos_stay_while_their_use_is_unknown(
    team: Team, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A logo a committed row might refer to is kept when the database can't be asked."""

    async def unreachable(*_: Any) -> set[StoredUpload]:
        raise ConnectionError("the database is unreachable")

    async def fail() -> None:
        raise RuntimeError("the command failed")

    before = team_logos()
    monkeypatch.setattr(database, "get_referenced_uploads", unreachable)
    with pytest.raises(RuntimeError, match="the command failed"):
        await replace_logo(team, fail)

    [kept] = team_logos() - before
    build_upload_path(UploadFolder.TEAM_LOGOS, kept).unlink()


async def test_a_write_that_fails_halfway_leaves_no_file(
    team: Team, monkeypatch: pytest.MonkeyPatch
) -> None:
    before = team_logos()
    original_open = aiofiles.open

    def open_then_fail(path: Any, mode: str = "r", *args: Any, **kwargs: Any) -> Any:
        Path(path).write_bytes(LOGO[:10])
        raise OSError("the disk is full")

    monkeypatch.setattr(aiofiles, "open", open_then_fail)
    with pytest.raises(OSError, match="the disk is full"):
        await replace_logo(team)

    monkeypatch.setattr(aiofiles, "open", original_open)
    assert team_logos() == before
