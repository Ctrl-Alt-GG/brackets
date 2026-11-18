from collections.abc import AsyncIterator, Sequence
from contextlib import asynccontextmanager
from typing import Annotated

import anyio
from fastapi import Depends, Request
from sqlalchemy import make_url
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from bracket.config import config
from bracket.sql.uploads import get_referenced_uploads
from bracket.utils.logging import logger
from bracket.utils.uploads import StoredUpload, new_uploads, remove_existing_upload

READ_METHODS = frozenset({"GET", "HEAD", "OPTIONS"})
# How long a failed command waits to find out which of its new files the database refers to.
UPLOAD_SETTLEMENT_SECONDS = 10

engine = create_async_engine(
    make_url(str(config.pg_dsn)).set(drivername="postgresql+asyncpg"),
    isolation_level="READ COMMITTED",
)
session_factory = async_sessionmaker(engine, expire_on_commit=False)
read_session_factory = async_sessionmaker(
    engine.execution_options(isolation_level="REPEATABLE READ", postgresql_readonly=True),
    expire_on_commit=False,
)


async def discard_unreferenced_uploads(uploads: Sequence[StoredUpload]) -> None:
    """
    Remove the files of a transaction that didn't commit, unless the database refers to them.

    Usually the transaction was rolled back and refers to none. When it failed while committing,
    whether it committed is unknown until the database is asked. If it can't be asked, the files
    stay: removing a file a committed row refers to would be worse than keeping an unused one.
    """
    try:
        with anyio.fail_after(UPLOAD_SETTLEMENT_SECONDS):
            async with session_scope(read_only=True) as session:
                referenced = await get_referenced_uploads(session, uploads)
    except Exception:
        logger.warning(
            "Kept %d new uploads of a failed command; whether they are used is unknown",
            len(uploads),
            exc_info=True,
        )
        return

    for upload in uploads:
        if upload not in referenced:
            await remove_existing_upload(upload.folder, upload.filename)


@asynccontextmanager
async def session_scope(*, read_only: bool = False) -> AsyncIterator[AsyncSession]:
    """
    One transaction, with a stable snapshot for reads and rollback on failure.

    Files stored for the transaction (`bracket.utils.uploads.new_uploads`) stay when it commits.
    When it fails, those the database doesn't refer to are removed, also when the request that
    owns the transaction is being cancelled.
    """
    factory = read_session_factory if read_only else session_factory
    session = factory()
    try:
        async with session, session.begin():
            yield session
    except BaseException:
        if uploads := new_uploads(session):
            with anyio.CancelScope(shield=True):
                await discard_unreferenced_uploads(uploads)
        raise


async def get_session(request: Request) -> AsyncIterator[AsyncSession]:
    # Function scope finishes the transaction before FastAPI sends the response.
    async with session_scope(read_only=request.method in READ_METHODS) as session:
        yield session


DbSession = Annotated[AsyncSession, Depends(get_session, scope="function")]
