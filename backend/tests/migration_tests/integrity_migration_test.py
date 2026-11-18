from decimal import Decimal

import pytest
from sqlalchemy import inspect, select
from sqlalchemy.ext.asyncio import AsyncEngine

from alembic import command
from bracket import orm
from bracket.utils.alembic import get_alembic_config
from tests.migration_tests.migrations_test import BASELINE, restore_baseline


@pytest.mark.parametrize(
    ("statements", "reason"),
    [
        (
            ("INSERT INTO players_x_teams(player_id,team_id) VALUES (1,1)",),
            "duplicate players_x_teams",
        ),
        (
            (
                (
                    "INSERT INTO stage_item_inputs(id,slot,tournament_id,stage_item_id) "
                    "VALUES (3,1,1,1)"
                ),
            ),
            "duplicate stage_item_inputs",
        ),
        (
            (
                (
                    "INSERT INTO users(id,email,name,password_hash,account_type) "
                    "VALUES (2,'another@example.org','Another','hash','REGULAR')"
                ),
                "INSERT INTO users_x_clubs(club_id,user_id,relation) VALUES (1,2,'OWNER')",
            ),
            "duplicate users_x_clubs",
        ),
        (("UPDATE matches SET stage_item_input1_score = -1 WHERE id = 1",), "ck_matches_scores"),
        (
            ("UPDATE rankings SET win_points = 0.1234567 WHERE id = 1",),
            "rankings.win_points cannot be represented exactly",
        ),
        (
            ("UPDATE rankings SET win_points = 0.00000000001 WHERE id = 1",),
            "rankings.win_points cannot be represented exactly",
        ),
        (
            ("UPDATE stage_item_inputs SET points = -0.00000000001 WHERE id = 1",),
            "stage_item_inputs.points cannot be represented exactly",
        ),
        (
            (
                (
                    "INSERT INTO tournaments(id,name,start_time,club_id,dashboard_public) "
                    "VALUES (2,'Other','2030-01-01T10:00:00Z',1,true)"
                ),
                (
                    "INSERT INTO rankings(id,tournament_id,position,win_points,"
                    "draw_points,loss_points,"
                    "add_score_points) VALUES (2,2,0,1,0.5,0,false)"
                ),
                "UPDATE stage_items SET ranking_id = 2 WHERE id = 1",
            ),
            "stage items and their rankings belong to different tournaments",
        ),
    ],
)
async def test_upgrade_rejects_incompatible_records_without_removing_data(
    migration_engine: AsyncEngine, statements: tuple[str, ...], reason: str
) -> None:
    await restore_baseline(migration_engine)
    async with migration_engine.begin() as connection:
        for statement in statements:
            await connection.exec_driver_sql(statement)
        before = (await connection.exec_driver_sql("SELECT count(*) FROM matches")).scalar_one()
    with pytest.raises(RuntimeError, match=reason):
        async with migration_engine.begin() as connection:
            await connection.run_sync(
                lambda conn: command.upgrade(get_alembic_config(conn), "head")
            )
    async with migration_engine.connect() as connection:
        columns = await connection.run_sync(lambda conn: inspect(conn).get_columns("stage_items"))
        assert "tournament_id" not in {column["name"] for column in columns}
        assert (
            await connection.exec_driver_sql("SELECT version_num FROM alembic_version")
        ).scalar_one() == BASELINE
        assert (
            await connection.exec_driver_sql("SELECT count(*) FROM matches")
        ).scalar_one() == before


async def test_upgrade_removes_float_artifacts_without_rounding_meaningful_precision(
    migration_engine: AsyncEngine,
) -> None:
    await restore_baseline(migration_engine)
    async with migration_engine.begin() as connection:
        await connection.exec_driver_sql(
            "UPDATE rankings SET win_points = 0.1::double precision + 0.2::double precision"
        )
        await connection.run_sync(lambda conn: command.upgrade(get_alembic_config(conn), "head"))
        assert await connection.scalar(select(orm.Ranking.win_points)) == Decimal("0.300000")


async def test_upgrade_gives_matches_without_timings_the_planned_ones(
    migration_engine: AsyncEngine,
) -> None:
    await restore_baseline(migration_engine)
    async with migration_engine.begin() as connection:
        await connection.exec_driver_sql(
            "UPDATE stages SET custom_duration_minutes = 25 WHERE id = 1"
        )
        await connection.exec_driver_sql(
            "UPDATE matches SET duration_minutes = NULL, margin_minutes = NULL WHERE id = 1"
        )
        await connection.run_sync(lambda conn: command.upgrade(get_alembic_config(conn), "head"))
        timings = await connection.execute(
            select(orm.Match.duration_minutes, orm.Match.margin_minutes)
        )
        # The stage's custom duration, and the tournament's default margin.
        assert timings.one() == (25, 5)
