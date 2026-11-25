import pytest
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import async_sessionmaker

from bracket import orm
from bracket.development_seed import TEAMS, create_dev_db
from tests.integration_tests.sql import isolated_schema


@pytest.mark.asyncio(loop_scope="session")
async def test_the_development_data_is_a_tournament_in_progress() -> None:
    # The seed replaces every table, so it runs in a schema of its own.
    async with isolated_schema() as isolated:
        factory = async_sessionmaker(isolated, expire_on_commit=False)
        async with factory() as session, session.begin():
            user_id = await create_dev_db(session)

            owner = await session.scalar(select(orm.TournamentOrganizer.user_id))
            assert owner == user_id
            for entity, expected in (
                (orm.TournamentTeam, TEAMS),
                (orm.TeamMember, 2 * TEAMS),
                (orm.TournamentPlayer, 2 * TEAMS),
            ):
                assert await session.scalar(select(func.count()).select_from(entity)) == expected
            planned = await session.scalar(
                select(func.count()).select_from(orm.Match).where(orm.Match.start_time.is_not(None))
            )
            assert (planned or 0) > 0
