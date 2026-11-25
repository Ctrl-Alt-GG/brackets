from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from uuid import uuid4

from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, create_async_engine
from sqlalchemy.schema import CreateSchema, DropSchema

from bracket import orm
from bracket.database import engine
from bracket.models.db.match import Match, MatchInsertable
from bracket.models.db.player import Player, PlayerInsertable
from bracket.models.db.ranking import Ranking, RankingInsertable
from bracket.models.db.round import Round, RoundInsertable
from bracket.models.db.stage import Stage, StageInsertable
from bracket.models.db.stage_item import StageItem, StageItemInsertable
from bracket.models.db.stage_item_inputs import (
    StageItemInputEmpty,
    StageItemInputFinal,
    StageItemInputInsertable,
)
from bracket.models.db.team import Team, TeamInsertable
from bracket.models.db.tournament import Tournament, TournamentInsertable
from bracket.models.db.user import UserBase, UserInDB
from bracket.models.enums import TournamentRole
from bracket.sql.matches import match_without_details
from bracket.sql.participation import LineupScope, sync_lineups
from bracket.sql.stage_item_inputs import get_stage_item_input_by_id
from bracket.sql.tournaments import sql_get_tournament
from bracket.utils.id_types import StageItemInputId, TeamId, TournamentId, UserId
from tests.dummy_records import DUMMY_RANKING1, DUMMY_TOURNAMENT
from tests.integration_tests.mocks import get_mock_token, get_mock_user
from tests.integration_tests.models import AuthContext


async def assert_row_count_and_clear(entity_type: type[orm.Base], expected_rows: int) -> None:
    async with AsyncSession(engine) as session, session.begin():
        row_count = await session.scalar(select(func.count()).select_from(entity_type))
        await session.execute(delete(entity_type))
    assert row_count == expected_rows, (row_count, expected_rows)


@asynccontextmanager
async def created_teams_and_players_removed() -> AsyncIterator[None]:
    """
    Teams and players outlive tournaments. Those created inside are deleted afterwards, after
    leaving the tournaments they joined.
    """
    async with AsyncSession(engine) as session:
        last_team = await session.scalar(select(func.coalesce(func.max(orm.Team.id), 0)))
        last_player = await session.scalar(select(func.coalesce(func.max(orm.Player.id), 0)))
    try:
        yield
    finally:
        async with AsyncSession(engine) as session, session.begin():
            await session.execute(
                delete(orm.TournamentTeam).where(orm.TournamentTeam.team_id > last_team)
            )
            await session.execute(delete(orm.Team).where(orm.Team.id > last_team))
            await session.execute(delete(orm.Player).where(orm.Player.id > last_player))


@asynccontextmanager
async def inserted_entity[EntityT: orm.Base](entity: EntityT) -> AsyncIterator[EntityT]:
    async with AsyncSession(engine, expire_on_commit=False) as session, session.begin():
        session.add(entity)
        await session.flush()
        entity_id = getattr(entity, "id")
    try:
        yield entity
    finally:
        async with AsyncSession(engine) as session, session.begin():
            await session.execute(
                delete(type(entity)).where(getattr(type(entity), "id") == entity_id)
            )


@asynccontextmanager
async def inserted_user(user: UserBase) -> AsyncIterator[UserInDB]:
    async with inserted_entity(orm.User(**user.model_dump())) as entity:
        yield UserInDB.model_validate(entity)


@asynccontextmanager
async def inserted_tournament(
    tournament: TournamentInsertable, owner_id: UserId | None = None
) -> AsyncIterator[Tournament]:
    """A tournament, which the account `owner_id` owns when one is given."""
    async with inserted_entity(orm.Tournament(**tournament.model_dump())) as entity:
        async with AsyncSession(engine) as session, session.begin():
            if owner_id is not None:
                session.add(
                    orm.TournamentOrganizer(
                        tournament_id=entity.id, user_id=owner_id, role=TournamentRole.OWNER
                    )
                )
            await session.flush()
            model = await sql_get_tournament(session, TournamentId(entity.id))
        yield model


@asynccontextmanager
async def inserted_organizer(
    tournament_id: TournamentId, user_id: UserId, role: TournamentRole
) -> AsyncIterator[None]:
    async with AsyncSession(engine) as session, session.begin():
        session.add(
            orm.TournamentOrganizer(tournament_id=tournament_id, user_id=user_id, role=role)
        )
    try:
        yield
    finally:
        async with AsyncSession(engine) as session, session.begin():
            await session.execute(
                delete(orm.TournamentOrganizer).where(
                    orm.TournamentOrganizer.tournament_id == tournament_id,
                    orm.TournamentOrganizer.user_id == user_id,
                )
            )


@asynccontextmanager
async def inserted_team(
    team: TeamInsertable, tournament_id: TournamentId | None = None, *, active: bool = True
) -> AsyncIterator[Team]:
    """A team, which takes part in `tournament_id` when one is given."""
    async with inserted_entity(orm.Team(**team.model_dump())) as entity:
        model = Team.model_validate(entity)
        if tournament_id is None:
            yield model
        else:
            async with inserted_participation(tournament_id, model.id, active=active):
                yield model


@asynccontextmanager
async def inserted_participation(
    tournament_id: TournamentId, team_id: TeamId, *, active: bool = True
) -> AsyncIterator[None]:
    """The team takes part in the tournament, with its active members in the lineup."""
    async with AsyncSession(engine) as session, session.begin():
        session.add(orm.TournamentTeam(tournament_id=tournament_id, team_id=team_id, active=active))
        await session.flush()
        await sync_lineups(session, LineupScope.of_tournament(tournament_id))
    try:
        yield
    finally:
        async with AsyncSession(engine) as session, session.begin():
            await session.execute(
                delete(orm.TournamentTeam).where(
                    orm.TournamentTeam.tournament_id == tournament_id,
                    orm.TournamentTeam.team_id == team_id,
                )
            )


@asynccontextmanager
async def inserted_ranking(ranking: RankingInsertable) -> AsyncIterator[Ranking]:
    async with inserted_entity(orm.Ranking(**ranking.model_dump())) as entity:
        yield Ranking.model_validate(entity)


@asynccontextmanager
async def inserted_player(player: PlayerInsertable) -> AsyncIterator[Player]:
    async with inserted_entity(orm.Player(**player.model_dump())) as entity:
        yield Player.model_validate(entity)


@asynccontextmanager
async def inserted_player_in_team(
    player: PlayerInsertable, team_id: TeamId, *, active: bool = True
) -> AsyncIterator[Player]:
    """
    A player in the team's roster. An active member joins the lineups of the team's open
    tournaments.
    """
    async with inserted_player(player) as model:
        async with AsyncSession(engine) as session, session.begin():
            session.add(orm.TeamMember(team_id=team_id, player_id=model.id, active=active))
            await session.flush()
            await sync_lineups(session, LineupScope.of_teams({team_id}))
        # Deleting the player at the end removes the membership and the lineup rows with it.
        yield model


@asynccontextmanager
async def inserted_stage(stage: StageInsertable) -> AsyncIterator[Stage]:
    async with inserted_entity(orm.Stage(**stage.model_dump())) as entity:
        yield Stage.model_validate(entity)


@asynccontextmanager
async def inserted_stage_item(stage_item: StageItemInsertable) -> AsyncIterator[StageItem]:
    async with AsyncSession(engine) as session:
        tournament_id = (
            await session.scalars(
                select(orm.Stage.tournament_id).where(orm.Stage.id == stage_item.stage_id)
            )
        ).one()
    async with inserted_entity(
        orm.StageItem(tournament_id=tournament_id, **stage_item.model_dump())
    ) as entity:
        yield StageItem.model_validate(entity)


@asynccontextmanager
async def inserted_stage_item_input(
    stage_item_input: StageItemInputInsertable,
) -> AsyncIterator[StageItemInputFinal | StageItemInputEmpty]:
    async with inserted_entity(orm.StageItemInput(**stage_item_input.model_dump())) as entity:
        async with AsyncSession(engine) as session:
            model = await get_stage_item_input_by_id(
                session, stage_item_input.tournament_id, StageItemInputId(entity.id)
            )
        assert isinstance(model, StageItemInputFinal | StageItemInputEmpty)
        yield model


@asynccontextmanager
async def inserted_round(round_: RoundInsertable) -> AsyncIterator[Round]:
    async with AsyncSession(engine) as session:
        tournament_id = (
            await session.scalars(
                select(orm.StageItem.tournament_id).where(orm.StageItem.id == round_.stage_item_id)
            )
        ).one()
    async with inserted_entity(
        orm.Round(tournament_id=tournament_id, **round_.model_dump())
    ) as entity:
        yield Round.model_validate(entity)


@asynccontextmanager
async def inserted_match(match: MatchInsertable) -> AsyncIterator[Match]:
    async with AsyncSession(engine) as session:
        tournament_id = (
            await session.scalars(
                select(orm.Round.tournament_id).where(orm.Round.id == match.round_id)
            )
        ).one()
    async with inserted_entity(
        orm.Match(tournament_id=tournament_id, **match.model_dump(exclude_computed_fields=True))
    ) as entity:
        yield match_without_details(entity)


@asynccontextmanager
async def inserted_auth_context(
    dashboard_endpoint: str | None = None,
) -> AsyncIterator[AuthContext]:
    """An organizer who owns a tournament. Details links are unique: give each its own."""
    mock_user = get_mock_user()
    async with (
        inserted_user(mock_user) as user_inserted,
        inserted_tournament(
            DUMMY_TOURNAMENT.model_copy(update={"dashboard_endpoint": dashboard_endpoint})
        ) as tournament_inserted,
        inserted_ranking(
            DUMMY_RANKING1.model_copy(update={"tournament_id": tournament_inserted.id})
        ) as ranking_inserted,
        inserted_organizer(tournament_inserted.id, user_inserted.id, TournamentRole.OWNER),
    ):
        yield AuthContext(
            headers={"Authorization": f"Bearer {get_mock_token(user_inserted)}"},
            user=user_inserted,
            tournament=tournament_inserted,
            ranking=ranking_inserted,
        )


@asynccontextmanager
async def isolated_schema() -> AsyncIterator[AsyncEngine]:
    """An engine whose tables live in a schema of their own, which is dropped afterwards."""
    schema_name = f"isolated_{uuid4().hex}"
    async with engine.begin() as connection:
        await connection.execute(CreateSchema(schema_name))
    isolated = create_async_engine(
        engine.url, connect_args={"server_settings": {"search_path": schema_name}}
    )
    try:
        yield isolated
    finally:
        await isolated.dispose()
        async with engine.begin() as connection:
            await connection.execute(DropSchema(schema_name, cascade=True))
