import random
from typing import Any, cast

from heliclockter import datetime_utc
from pydantic import BaseModel
from sqlalchemy import inspect
from sqlalchemy.ext.asyncio import AsyncConnection, AsyncSession

from bracket import orm
from bracket.config import Environment, config, environment
from bracket.logic.planning.matches import schedule_all_matches
from bracket.logic.ranking.calculation import (
    recalculate_ranking_for_stage_item,
)
from bracket.logic.scheduling.builder import build_matches_for_stage_item
from bracket.models.db.account import UserAccountType
from bracket.models.db.club import ClubInsertable
from bracket.models.db.match import Match, MatchBody
from bracket.models.db.player import PlayerInsertable
from bracket.models.db.player_x_team import PlayerXTeamInsertable
from bracket.models.db.ranking import RankingInsertable
from bracket.models.db.round import RoundInsertable
from bracket.models.db.stage import StageInsertable
from bracket.models.db.stage_item import (
    StageItemInsertable,
    StageItemWithInputsCreate,
)
from bracket.models.db.stage_item_inputs import (
    StageItemInputCreateBodyFinal,
    StageItemInputCreateBodyTentative,
)
from bracket.models.db.team import TeamInsertable
from bracket.models.db.tournament import TournamentInsertable
from bracket.models.db.user import UserInsertable
from bracket.models.db.user_x_club import UserXClubInsertable, UserXClubRelation
from bracket.sql.matches import sql_update_match
from bracket.sql.stage_items import get_stage_item, sql_create_stage_item_with_inputs
from bracket.sql.stages import get_full_tournament_details
from bracket.sql.users import create_user, get_user
from bracket.utils.alembic import alembic_stamp_head
from bracket.utils.dummy_records import (
    DUMMY_CLUB,
    DUMMY_PLAYER1,
    DUMMY_PLAYER2,
    DUMMY_PLAYER3,
    DUMMY_PLAYER4,
    DUMMY_PLAYER5,
    DUMMY_PLAYER6,
    DUMMY_PLAYER7,
    DUMMY_PLAYER8,
    DUMMY_PLAYER_X_TEAM,
    DUMMY_RANKING1,
    DUMMY_STAGE1,
    DUMMY_STAGE2,
    DUMMY_STAGE_ITEM1,
    DUMMY_STAGE_ITEM2,
    DUMMY_STAGE_ITEM3,
    DUMMY_TEAM1,
    DUMMY_TEAM2,
    DUMMY_TEAM3,
    DUMMY_TEAM4,
    DUMMY_TOURNAMENT,
    DUMMY_USER,
)
from bracket.utils.id_types import (
    ClubId,
    PlayerId,
    StageId,
    TeamId,
    TournamentId,
    UserId,
)
from bracket.utils.logging import logger
from bracket.utils.security import hash_password
from bracket.utils.types import assert_some


async def create_admin_user(conn: AsyncSession) -> UserId:
    assert config.admin_email
    assert config.admin_password

    user = await create_user(
        conn,
        UserInsertable(
            name="Admin",
            email=config.admin_email,
            password_hash=hash_password(config.admin_password),
            created=datetime_utc.now(),
            account_type=UserAccountType.REGULAR,
        ),
    )
    return user.id


async def init_db_when_empty(conn: AsyncConnection) -> UserId | None:
    table_names = await conn.run_sync(lambda connection: inspect(connection).get_table_names())
    empty = len(table_names) <= 1
    if empty:
        logger.warning("Empty db detected, creating tables...")
        await conn.run_sync(orm.Base.metadata.create_all)
        await conn.run_sync(alembic_stamp_head)

    if not (config.admin_email and config.admin_password):
        return None

    async with AsyncSession(bind=conn, expire_on_commit=False) as session:
        if empty or (
            environment is Environment.DEVELOPMENT
            and await get_user(session, config.admin_email) is None
        ):
            logger.warning("Admin user missing, creating admin user...")
            user_id = await create_admin_user(session)
            await session.flush()
            return user_id

    return None


async def sql_create_dev_db(conn: AsyncSession) -> UserId:
    # TODO: refactor into smaller functions
    # pylint: disable=too-many-statements
    assert environment is not Environment.PRODUCTION

    logger.warning("Initializing database with dummy records")
    connection = await conn.connection()
    await connection.run_sync(orm.Base.metadata.drop_all)
    await connection.run_sync(orm.Base.metadata.create_all)
    conn.expunge_all()
    real_user_id = await init_db_when_empty(connection)
    await connection.run_sync(alembic_stamp_head)

    entity_lookup: dict[type[BaseModel], type[orm.Base]] = {
        UserInsertable: orm.User,
        ClubInsertable: orm.Club,
        StageInsertable: orm.Stage,
        TeamInsertable: orm.Team,
        UserXClubInsertable: orm.UserXClub,
        PlayerXTeamInsertable: orm.PlayerXTeam,
        PlayerInsertable: orm.Player,
        RoundInsertable: orm.Round,
        Match: orm.Match,
        TournamentInsertable: orm.Tournament,
        StageItemInsertable: orm.StageItem,
        RankingInsertable: orm.Ranking,
    }

    async def insert_dummy(
        obj_to_insert: BaseModel, update_data: dict[str, Any] | None = None
    ) -> int:
        entity_type = entity_lookup[type(obj_to_insert)]
        values = obj_to_insert.model_copy(update=update_data or {}).model_dump()
        columns = {attribute.key for attribute in inspect(entity_type).column_attrs}
        entity = entity_type(**{key: value for key, value in values.items() if key in columns})
        conn.add(entity)
        await conn.flush()
        return cast("int", getattr(entity, "id"))

    user_id_1 = UserId(await insert_dummy(DUMMY_USER))
    club_id_1 = ClubId(await insert_dummy(DUMMY_CLUB))

    await insert_dummy(
        UserXClubInsertable(user_id=user_id_1, club_id=club_id_1, relation=UserXClubRelation.OWNER),
    )

    if real_user_id is not None:
        await insert_dummy(
            UserXClubInsertable(
                user_id=real_user_id, club_id=club_id_1, relation=UserXClubRelation.OWNER
            )
        )

    tournament_id_1 = TournamentId(await insert_dummy(DUMMY_TOURNAMENT, {"club_id": club_id_1}))
    stage_id_1 = StageId(await insert_dummy(DUMMY_STAGE1, {"tournament_id": tournament_id_1}))
    stage_id_2 = StageId(await insert_dummy(DUMMY_STAGE2, {"tournament_id": tournament_id_1}))

    await insert_dummy(DUMMY_RANKING1, {"tournament_id": tournament_id_1})

    team_id_1 = TeamId(await insert_dummy(DUMMY_TEAM1, {"tournament_id": tournament_id_1}))
    team_id_2 = TeamId(await insert_dummy(DUMMY_TEAM2, {"tournament_id": tournament_id_1}))
    team_id_3 = TeamId(await insert_dummy(DUMMY_TEAM3, {"tournament_id": tournament_id_1}))
    team_id_4 = TeamId(await insert_dummy(DUMMY_TEAM4, {"tournament_id": tournament_id_1}))
    team_id_5 = TeamId(
        await insert_dummy(DUMMY_TEAM4, {"name": "Team 5", "tournament_id": tournament_id_1})
    )
    team_id_6 = TeamId(
        await insert_dummy(DUMMY_TEAM4, {"name": "Team 6", "tournament_id": tournament_id_1})
    )
    team_id_7 = TeamId(
        await insert_dummy(DUMMY_TEAM4, {"name": "Team 7", "tournament_id": tournament_id_1})
    )
    team_id_8 = TeamId(
        await insert_dummy(DUMMY_TEAM4, {"name": "Team 8", "tournament_id": tournament_id_1})
    )

    player_id_1 = PlayerId(await insert_dummy(DUMMY_PLAYER1, {"tournament_id": tournament_id_1}))
    player_id_2 = PlayerId(await insert_dummy(DUMMY_PLAYER2, {"tournament_id": tournament_id_1}))
    player_id_3 = PlayerId(await insert_dummy(DUMMY_PLAYER3, {"tournament_id": tournament_id_1}))
    player_id_4 = PlayerId(await insert_dummy(DUMMY_PLAYER4, {"tournament_id": tournament_id_1}))
    player_id_5 = PlayerId(await insert_dummy(DUMMY_PLAYER5, {"tournament_id": tournament_id_1}))
    player_id_6 = PlayerId(await insert_dummy(DUMMY_PLAYER6, {"tournament_id": tournament_id_1}))
    player_id_7 = PlayerId(await insert_dummy(DUMMY_PLAYER7, {"tournament_id": tournament_id_1}))
    player_id_8 = PlayerId(await insert_dummy(DUMMY_PLAYER8, {"tournament_id": tournament_id_1}))

    player_id_9 = PlayerId(
        await insert_dummy(DUMMY_PLAYER8, {"name": "Player 09", "tournament_id": tournament_id_1})
    )
    player_id_10 = PlayerId(
        await insert_dummy(DUMMY_PLAYER8, {"name": "Player 10", "tournament_id": tournament_id_1})
    )
    player_id_11 = PlayerId(
        await insert_dummy(DUMMY_PLAYER8, {"name": "Player 11", "tournament_id": tournament_id_1})
    )
    player_id_12 = PlayerId(
        await insert_dummy(DUMMY_PLAYER8, {"name": "Player 12", "tournament_id": tournament_id_1})
    )
    player_id_13 = PlayerId(
        await insert_dummy(DUMMY_PLAYER8, {"name": "Player 13", "tournament_id": tournament_id_1})
    )
    player_id_14 = PlayerId(
        await insert_dummy(DUMMY_PLAYER8, {"name": "Player 14", "tournament_id": tournament_id_1})
    )
    player_id_15 = PlayerId(
        await insert_dummy(DUMMY_PLAYER8, {"name": "Player 15", "tournament_id": tournament_id_1})
    )
    player_id_16 = PlayerId(
        await insert_dummy(DUMMY_PLAYER8, {"name": "Player 16", "tournament_id": tournament_id_1})
    )

    await insert_dummy(DUMMY_PLAYER_X_TEAM, {"player_id": player_id_1, "team_id": team_id_1})
    await insert_dummy(DUMMY_PLAYER_X_TEAM, {"player_id": player_id_2, "team_id": team_id_1})
    await insert_dummy(DUMMY_PLAYER_X_TEAM, {"player_id": player_id_3, "team_id": team_id_2})
    await insert_dummy(DUMMY_PLAYER_X_TEAM, {"player_id": player_id_4, "team_id": team_id_2})
    await insert_dummy(DUMMY_PLAYER_X_TEAM, {"player_id": player_id_5, "team_id": team_id_3})
    await insert_dummy(DUMMY_PLAYER_X_TEAM, {"player_id": player_id_6, "team_id": team_id_3})
    await insert_dummy(DUMMY_PLAYER_X_TEAM, {"player_id": player_id_7, "team_id": team_id_4})
    await insert_dummy(DUMMY_PLAYER_X_TEAM, {"player_id": player_id_8, "team_id": team_id_4})
    await insert_dummy(DUMMY_PLAYER_X_TEAM, {"player_id": player_id_9, "team_id": team_id_5})
    await insert_dummy(DUMMY_PLAYER_X_TEAM, {"player_id": player_id_10, "team_id": team_id_5})
    await insert_dummy(DUMMY_PLAYER_X_TEAM, {"player_id": player_id_11, "team_id": team_id_6})
    await insert_dummy(DUMMY_PLAYER_X_TEAM, {"player_id": player_id_12, "team_id": team_id_6})
    await insert_dummy(DUMMY_PLAYER_X_TEAM, {"player_id": player_id_13, "team_id": team_id_7})
    await insert_dummy(DUMMY_PLAYER_X_TEAM, {"player_id": player_id_14, "team_id": team_id_7})
    await insert_dummy(DUMMY_PLAYER_X_TEAM, {"player_id": player_id_15, "team_id": team_id_8})
    await insert_dummy(DUMMY_PLAYER_X_TEAM, {"player_id": player_id_16, "team_id": team_id_8})

    stage_item_1 = await sql_create_stage_item_with_inputs(
        conn,
        tournament_id_1,
        StageItemWithInputsCreate(
            stage_id=stage_id_1,
            name=DUMMY_STAGE_ITEM1.name,
            team_count=DUMMY_STAGE_ITEM1.team_count,
            type=DUMMY_STAGE_ITEM1.type,
            inputs=[
                StageItemInputCreateBodyFinal(
                    slot=1,
                    team_id=team_id_1,
                ),
                StageItemInputCreateBodyFinal(
                    slot=2,
                    team_id=team_id_2,
                ),
                StageItemInputCreateBodyFinal(
                    slot=3,
                    team_id=team_id_3,
                ),
                StageItemInputCreateBodyFinal(
                    slot=4,
                    team_id=team_id_4,
                ),
            ],
        ),
    )
    stage_item_2 = await sql_create_stage_item_with_inputs(
        conn,
        tournament_id_1,
        StageItemWithInputsCreate(
            stage_id=stage_id_1,
            name=DUMMY_STAGE_ITEM2.name,
            team_count=DUMMY_STAGE_ITEM2.team_count,
            type=DUMMY_STAGE_ITEM2.type,
            inputs=[
                StageItemInputCreateBodyFinal(
                    slot=1,
                    team_id=team_id_5,
                ),
                StageItemInputCreateBodyFinal(
                    slot=2,
                    team_id=team_id_6,
                ),
                StageItemInputCreateBodyFinal(
                    slot=3,
                    team_id=team_id_7,
                ),
                StageItemInputCreateBodyFinal(
                    slot=4,
                    team_id=team_id_8,
                ),
            ],
        ),
    )
    stage_item_3 = await sql_create_stage_item_with_inputs(
        conn,
        tournament_id_1,
        StageItemWithInputsCreate(
            stage_id=stage_id_2,
            name=DUMMY_STAGE_ITEM3.name,
            team_count=DUMMY_STAGE_ITEM3.team_count,
            type=DUMMY_STAGE_ITEM3.type,
            inputs=[
                StageItemInputCreateBodyTentative(
                    slot=1,
                    winner_from_stage_item_id=stage_item_1.id,
                    winner_position=1,
                ),
                StageItemInputCreateBodyTentative(
                    slot=2,
                    winner_from_stage_item_id=stage_item_1.id,
                    winner_position=2,
                ),
                StageItemInputCreateBodyTentative(
                    slot=3,
                    winner_from_stage_item_id=stage_item_2.id,
                    winner_position=1,
                ),
                StageItemInputCreateBodyTentative(
                    slot=4,
                    winner_from_stage_item_id=stage_item_2.id,
                    winner_position=2,
                ),
            ],
        ),
    )

    await build_matches_for_stage_item(conn, stage_item_1, tournament_id_1)
    await build_matches_for_stage_item(conn, stage_item_2, tournament_id_1)
    await build_matches_for_stage_item(conn, stage_item_3, tournament_id_1)

    for stage in await get_full_tournament_details(conn, tournament_id_1):
        for stage_item in stage.stage_items:
            for round_ in stage_item.rounds:
                for match in round_.matches:
                    await sql_update_match(
                        conn,
                        match_id=assert_some(match.id),
                        match=MatchBody.model_validate(
                            {
                                **match.model_dump(),
                                "stage_item_input1_score": random.randint(0, 10),
                                "stage_item_input2_score": random.randint(0, 10),
                            }
                        ),
                    )

    for _stage_item in (stage_item_1, stage_item_2, stage_item_3):
        stage_item_with_rounds = await get_stage_item(conn, tournament_id_1, _stage_item.id)
        await recalculate_ranking_for_stage_item(conn, tournament_id_1, stage_item_with_rounds)

    await schedule_all_matches(conn, tournament_id_1)
    return user_id_1
