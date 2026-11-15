from decimal import Decimal
from pathlib import Path

import asyncpg  # type: ignore[import-untyped]
from sqlalchemy import inspect, select
from sqlalchemy.ext.asyncio import AsyncEngine

from alembic import command
from bracket import orm
from bracket.utils.alembic import get_alembic_config
from bracket.utils.db_init import init_db_when_empty

BASELINE = "b2e5c8d1f4a7"
SCHEMA = Path(__file__).with_name("assets") / f"{BASELINE}.sql"


async def restore_baseline(engine: AsyncEngine) -> None:
    url = engine.url.set(drivername="postgresql")
    connection = await asyncpg.connect(url.render_as_string(hide_password=False))
    try:
        await connection.execute(SCHEMA.read_text())
        await connection.execute("SET search_path TO public")
        # Historical fixture data exercises every newly scoped parent/child reference.
        await connection.execute("""
            INSERT INTO users(id,email,name,password_hash,account_type)
                VALUES (1,'owner@example.org','Owner','hash','REGULAR');
            INSERT INTO clubs(id,name) VALUES (1,'Legacy event');
            INSERT INTO users_x_clubs(club_id,user_id,relation) VALUES (1,1,'OWNER');
            INSERT INTO tournaments(id,name,start_time,club_id,dashboard_public)
                VALUES (1,'Legacy tournament','2030-01-01T10:00:00Z',1,true);
            INSERT INTO stages(id,name,tournament_id) VALUES (1,'Groups',1);
            INSERT INTO rankings(id,tournament_id,position,win_points,draw_points,loss_points,
                add_score_points) VALUES (1,1,0,0.125,0.0625,0,false);
            INSERT INTO stage_items(id,name,stage_id,team_count,ranking_id,type)
                VALUES (1,'Group',1,2,1,'ROUND_ROBIN');
            INSERT INTO teams(id,name,tournament_id) VALUES (1,'Alpha',1),(2,'Bravo',1);
            INSERT INTO players(id,name,tournament_id,elo_score,swiss_score,wins,draws,losses)
                VALUES (1,'Alice',1,1200,0,0,0,0);
            INSERT INTO players_x_teams(player_id,team_id) VALUES (1,1);
            INSERT INTO stage_item_inputs(id,slot,tournament_id,stage_item_id,team_id,points)
                VALUES (1,1,1,1,1,0.125),(2,2,1,1,2,0);
            INSERT INTO rounds(id,name,is_draft,stage_item_id) VALUES (1,'Round 01',false,1);
            INSERT INTO matches(id,round_id,stage_item_input1_id,stage_item_input2_id,
                stage_item_input1_score,stage_item_input2_score,stage_item_input1_conflict,
                stage_item_input2_conflict,duration_minutes,margin_minutes)
                VALUES (1,1,1,2,2,1,false,false,15,5);
        """)
    finally:
        await connection.close()
    async with engine.begin() as connection:
        await connection.run_sync(lambda conn: command.stamp(get_alembic_config(conn), BASELINE))


async def test_upgrade_preserves_data_and_matches_metadata(migration_engine: AsyncEngine) -> None:
    await restore_baseline(migration_engine)
    async with migration_engine.begin() as connection:
        await connection.run_sync(lambda conn: command.upgrade(get_alembic_config(conn), "head"))
        await connection.run_sync(lambda conn: command.check(get_alembic_config(conn)))
        for entity in (orm.StageItem, orm.Round, orm.Match, orm.PlayerXTeam):
            assert list(await connection.scalars(select(entity.tournament_id))) == [1]
        assert await connection.scalar(select(orm.Ranking.win_points)) == Decimal("0.125")
        assert await connection.scalar(
            select(orm.StageItemInput.points).where(orm.StageItemInput.id == 1)
        ) == Decimal("0.125")
        assert await connection.scalar(select(orm.Match.stage_item_input1_score)) == 2
        await connection.run_sync(
            lambda conn: command.downgrade(get_alembic_config(conn), BASELINE)
        )
        for table in ("stage_items", "rounds", "matches", "players_x_teams"):
            columns = await connection.run_sync(lambda conn: inspect(conn).get_columns(table))
            assert "tournament_id" not in {column["name"] for column in columns}
        await connection.run_sync(lambda conn: command.upgrade(get_alembic_config(conn), "head"))
        await connection.run_sync(lambda conn: command.check(get_alembic_config(conn)))


async def test_empty_database_bootstrap_matches_metadata(migration_engine: AsyncEngine) -> None:
    async with migration_engine.begin() as connection:
        await init_db_when_empty(connection)
        await connection.run_sync(lambda conn: command.check(get_alembic_config(conn)))
