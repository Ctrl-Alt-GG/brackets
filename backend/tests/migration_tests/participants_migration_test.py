"""Events go away, and teams and players stop belonging to one tournament."""

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncEngine

from alembic import command
from bracket import orm
from bracket.models.enums import TournamentRole
from bracket.utils.alembic import get_alembic_config
from tests.migration_tests.migrations_test import restore_baseline

# The migration before this change.
EVENTS = "e1d4f7a2b9c3"


async def upgrade(engine: AsyncEngine, *statements: str) -> None:
    """Upgrade the baseline with rows that these statements add just before events are removed."""
    await restore_baseline(engine)
    async with engine.begin() as connection:
        await connection.run_sync(lambda conn: command.upgrade(get_alembic_config(conn), EVENTS))
        for statement in statements:
            await connection.exec_driver_sql(statement)
        await connection.run_sync(lambda conn: command.upgrade(get_alembic_config(conn), "head"))


async def test_who_ran_an_event_runs_each_of_its_tournaments(migration_engine: AsyncEngine) -> None:
    await upgrade(
        migration_engine,
        "INSERT INTO users(id,email,name,password_hash,account_type) "
        "VALUES (2,'helper@example.org','Helper','hash','REGULAR')",
        "INSERT INTO users_x_clubs(club_id,user_id,relation) VALUES (1,2,'COLLABORATOR')",
        "INSERT INTO tournaments(id,name,start_time,club_id,dashboard_public) "
        "VALUES (2,'Second tournament','2030-01-02T10:00:00Z',1,false)",
    )
    async with migration_engine.connect() as connection:
        organizers = (
            await connection.execute(
                select(
                    orm.TournamentOrganizer.tournament_id,
                    orm.TournamentOrganizer.user_id,
                    orm.TournamentOrganizer.role,
                ).order_by(orm.TournamentOrganizer.tournament_id, orm.TournamentOrganizer.user_id)
            )
        ).all()
    assert organizers == [
        (1, 1, TournamentRole.OWNER),
        (1, 2, TournamentRole.COLLABORATOR),
        (2, 1, TournamentRole.OWNER),
        (2, 2, TournamentRole.COLLABORATOR),
    ]


async def test_a_player_stays_active_in_the_first_team_they_joined(
    migration_engine: AsyncEngine,
) -> None:
    """
    Alice was in both teams, as `players_can_be_in_multiple_teams` allowed. Bob was marked
    inactive. Neither membership is lost, but only active members play.
    """
    await upgrade(
        migration_engine,
        "UPDATE tournaments SET players_can_be_in_multiple_teams = true",
        "INSERT INTO players(id,name,tournament_id,elo_score,swiss_score,wins,draws,losses,active) "
        "VALUES (2,'Bob',1,1200,0,0,0,0,false)",
        "INSERT INTO players_x_teams(player_id,team_id,tournament_id) VALUES (1,2,1),(2,2,1)",
    )
    async with migration_engine.connect() as connection:
        members = (
            await connection.execute(
                select(
                    orm.TeamMember.team_id, orm.TeamMember.player_id, orm.TeamMember.active
                ).order_by(orm.TeamMember.team_id, orm.TeamMember.player_id)
            )
        ).all()
        lineup = (
            await connection.execute(
                select(orm.TournamentPlayer.player_id, orm.TournamentPlayer.team_id)
            )
        ).all()
    assert members == [(1, 1, True), (2, 1, False), (2, 2, False)]
    assert lineup == [(1, 1)]


async def test_a_downgrade_refuses_teams_that_take_part_in_several_tournaments(
    migration_engine: AsyncEngine,
) -> None:
    await upgrade(migration_engine)
    async with migration_engine.begin() as connection:
        await connection.exec_driver_sql(
            "INSERT INTO tournaments(id,name,start_time,dashboard_public) "
            "VALUES (2,'Second tournament','2030-01-02T10:00:00Z',false)"
        )
        await connection.exec_driver_sql(
            "INSERT INTO tournament_teams(tournament_id,team_id) VALUES (2,1)"
        )
    with pytest.raises(RuntimeError, match="teams that take part in no tournament or in several"):
        async with migration_engine.begin() as connection:
            await connection.run_sync(
                lambda conn: command.downgrade(get_alembic_config(conn), EVENTS)
            )
