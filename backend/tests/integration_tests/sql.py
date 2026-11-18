from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from uuid import uuid4

from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, create_async_engine
from sqlalchemy.schema import CreateSchema, DropSchema

from bracket import orm
from bracket.database import engine
from bracket.models.db.club import Club, ClubInsertable
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
from bracket.models.db.user_x_club import UserXClub, UserXClubInsertable
from bracket.models.enums import UserXClubRelation
from bracket.sql.matches import match_without_details
from bracket.sql.stage_item_inputs import get_stage_item_input_by_id
from bracket.sql.tournaments import sql_get_tournament
from bracket.utils.id_types import StageItemInputId, TeamId, TournamentId
from tests.dummy_records import DUMMY_CLUB, DUMMY_RANKING1, DUMMY_TOURNAMENT
from tests.integration_tests.mocks import get_mock_token, get_mock_user
from tests.integration_tests.models import AuthContext


async def assert_row_count_and_clear(entity_type: type[orm.Base], expected_rows: int) -> None:
    async with AsyncSession(engine) as session, session.begin():
        row_count = await session.scalar(select(func.count()).select_from(entity_type))
        await session.execute(delete(entity_type))
    assert row_count == expected_rows, (row_count, expected_rows)


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
async def inserted_club(club: ClubInsertable) -> AsyncIterator[Club]:
    async with inserted_entity(orm.Club(**club.model_dump())) as entity:
        yield Club.model_validate(entity)


@asynccontextmanager
async def inserted_tournament(tournament: TournamentInsertable) -> AsyncIterator[Tournament]:
    async with inserted_entity(orm.Tournament(**tournament.model_dump())) as entity:
        async with AsyncSession(engine) as session:
            model = await sql_get_tournament(session, TournamentId(entity.id))
        yield model


@asynccontextmanager
async def inserted_team(team: TeamInsertable) -> AsyncIterator[Team]:
    async with inserted_entity(orm.Team(**team.model_dump())) as entity:
        yield Team.model_validate(entity)


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
    player: PlayerInsertable, team_id: TeamId
) -> AsyncIterator[Player]:
    async with inserted_player(player) as model:
        async with inserted_entity(
            orm.PlayerXTeam(tournament_id=model.tournament_id, player_id=model.id, team_id=team_id)
        ):
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
async def inserted_user_x_club(user_x_club: UserXClubInsertable) -> AsyncIterator[UserXClub]:
    async with inserted_entity(orm.UserXClub(**user_x_club.model_dump())) as entity:
        yield UserXClub.model_validate(entity)


@asynccontextmanager
async def inserted_auth_context(
    dashboard_endpoint: str | None = None,
) -> AsyncIterator[AuthContext]:
    """An organizer with an event and a tournament. Details links are unique: give each its own."""
    mock_user = get_mock_user()
    async with (
        inserted_user(mock_user) as user_inserted,
        inserted_club(DUMMY_CLUB) as club_inserted,
        inserted_tournament(
            DUMMY_TOURNAMENT.model_copy(
                update={"club_id": club_inserted.id, "dashboard_endpoint": dashboard_endpoint}
            )
        ) as tournament_inserted,
        inserted_ranking(
            DUMMY_RANKING1.model_copy(update={"tournament_id": tournament_inserted.id})
        ) as ranking_inserted,
        inserted_user_x_club(
            UserXClubInsertable(
                user_id=user_inserted.id,
                club_id=club_inserted.id,
                relation=UserXClubRelation.OWNER,
            )
        ) as user_x_club_inserted,
    ):
        yield AuthContext(
            headers={"Authorization": f"Bearer {get_mock_token(user_inserted)}"},
            user=user_inserted,
            club=club_inserted,
            tournament=tournament_inserted,
            user_x_club=user_x_club_inserted,
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
