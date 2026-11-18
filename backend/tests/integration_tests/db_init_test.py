import pytest
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import async_sessionmaker

from bracket import orm
from bracket.development_seed import create_dev_db
from bracket.logic.users import delete_user_and_owned_clubs
from tests.integration_tests.sql import isolated_schema


@pytest.mark.asyncio(loop_scope="session")
async def test_the_development_data_goes_with_its_owner() -> None:
    # The seed replaces every table, so it runs in a schema of its own.
    async with isolated_schema() as isolated:
        factory = async_sessionmaker(isolated, expire_on_commit=False)
        async with factory() as session, session.begin():
            user_id = await create_dev_db(session)
            assert (await session.scalar(select(func.count()).select_from(orm.Match)) or 0) > 0

            uploads = await delete_user_and_owned_clubs(session, user_id)

            assert len(uploads) == 1
            for entity in (orm.User, orm.Club, orm.Tournament, orm.Match):
                assert await session.scalar(select(func.count()).select_from(entity)) == 0
