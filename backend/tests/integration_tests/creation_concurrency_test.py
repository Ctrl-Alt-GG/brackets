"""
The rules that cover several records hold when two commands check them at the same time: the
second waits for the first and sees what it did.
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
from bracket.logic.participation import add_teams
from bracket.logic.subscriptions import LIMITS, Limit
from bracket.logic.teams import create_team, update_team
from bracket.logic.tournaments import create_tournament
from bracket.models.db.team import TeamBody, TeamMemberBody, TeamWithMembers
from bracket.models.db.tournament import Tournament, TournamentBody
from bracket.models.db.user import UserInDB, UserPublic
from bracket.models.enums import UserAccountType
from bracket.sql.participation import get_lineups
from bracket.sql.players import insert_players
from bracket.utils.id_types import PlayerId
from tests.dummy_records import DUMMY_MOCK_TIME, DUMMY_USER
from tests.integration_tests.sql import inserted_user

pytestmark = pytest.mark.asyncio(loop_scope="session")

Command = Callable[[], Coroutine[Any, Any, Any]]


def public(user: UserInDB) -> UserPublic:
    return UserPublic.model_validate(user.model_dump(exclude={"password_hash"}))


def tournament_body(name: str) -> TournamentBody:
    return TournamentBody(
        name=name,
        start_time=DUMMY_MOCK_TIME,
        dashboard_public=False,
        duration_minutes=10,
        margin_minutes=5,
    )


@asynccontextmanager
async def organizer(name: str) -> AsyncIterator[UserPublic]:
    """An account, whose tournaments are deleted with it."""
    async with inserted_user(
        DUMMY_USER.model_copy(update={"email": f"{name}@example.org", "name": name})
    ) as user:
        try:
            yield public(user)
        finally:
            async with session_scope() as session:
                owned = select(orm.TournamentOrganizer.tournament_id).where(
                    orm.TournamentOrganizer.user_id == user.id
                )
                await session.execute(delete(orm.Tournament).where(orm.Tournament.id.in_(owned)))


@asynccontextmanager
async def tournament_with_teams(
    owner: UserPublic, *team_names: str
) -> AsyncIterator[tuple[Tournament, list[TeamWithMembers], PlayerId]]:
    """A tournament, teams that have no members yet, and a player who is in no team."""
    async with session_scope() as session:
        tournament = await create_tournament(session, tournament_body("Cup"), owner)
        [player_id] = await insert_players(session, ["Alex"])
        teams = [await create_team(session, TeamBody(name=name), owner) for name in team_names]
    try:
        yield tournament, teams, player_id
    finally:
        async with session_scope() as session:
            await session.execute(delete(orm.Tournament).where(orm.Tournament.id == tournament.id))
            await session.execute(
                delete(orm.Team).where(orm.Team.id.in_([team.id for team in teams]))
            )
            await session.execute(delete(orm.Player).where(orm.Player.id == player_id))


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


async def test_two_tournaments_for_the_last_place(monkeypatch: pytest.MonkeyPatch) -> None:
    async with organizer("owner") as owner:
        monkeypatch.setitem(LIMITS[UserAccountType.REGULAR], Limit.TOURNAMENTS, 1)

        async def create(session: AsyncSession) -> None:
            await create_tournament(session, tournament_body("First"), owner)

        async def create_another() -> None:
            async with session_scope() as session:
                await create_tournament(session, tournament_body("Second"), owner)

        assert await refused(race(create, create_another, "NO KEY UPDATE")) == (
            "That would be more than the 1 tournaments an account can own."
        )
        async with session_scope(read_only=True) as session:
            count = await session.scalar(
                select(func.count())
                .select_from(orm.TournamentOrganizer)
                .where(orm.TournamentOrganizer.user_id == owner.id)
            )
        assert count == 1


async def test_two_rosters_that_take_one_player_into_a_tournament() -> None:
    """Both teams take part, so the second roster to be saved sees the first one's player."""
    async with (
        organizer("owner") as owner,
        tournament_with_teams(owner, "First", "Second") as (tournament, teams, player_id),
    ):
        first, second = teams
        async with session_scope() as session:
            await add_teams(session, tournament, {first.id, second.id}, owner)
        roster = [TeamMemberBody(player_id=player_id)]

        async def join_first(session: AsyncSession) -> None:
            await update_team(session, first.id, TeamBody(name="First", members=roster), owner)

        async def join_second() -> None:
            async with session_scope() as session:
                await update_team(
                    session, second.id, TeamBody(name="Second", members=roster), owner
                )

        assert await refused(race(join_first, join_second, "FOR UPDATE")) == (
            "Alex can't play for both First and Second in Cup. A player can be an active member "
            "of only one of a tournament's teams."
        )


async def test_a_team_that_joins_while_its_roster_changes() -> None:
    """The roster change waits for the team to join, and then reaches the tournament's lineup."""
    async with (
        organizer("owner") as owner,
        tournament_with_teams(owner, "Joining") as (tournament, [team], player_id),
    ):

        async def join(session: AsyncSession) -> None:
            await add_teams(session, tournament, {team.id}, owner)

        async def change_roster() -> None:
            async with session_scope() as session:
                await update_team(
                    session,
                    team.id,
                    TeamBody(name="Joining", members=[TeamMemberBody(player_id=player_id)]),
                    owner,
                )

        await race(join, change_roster, "NO KEY UPDATE")
        async with session_scope(read_only=True) as session:
            assert await get_lineups(session, tournament.id) == {team.id: frozenset({player_id})}
