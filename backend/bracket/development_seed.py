"""
A development database with an example tournament. Only the CLI's `create-dev-db` imports this;
production startup uses `bracket.bootstrap`.
"""

import random
from datetime import UTC, datetime
from decimal import Decimal

from sqlalchemy.ext.asyncio import AsyncSession

from bracket import orm
from bracket.bootstrap import init_db_when_empty
from bracket.config import Environment, environment
from bracket.logic.planning.matches import schedule_all_matches
from bracket.logic.ranking.calculation import recalculate_ranking_for_stage_item
from bracket.logic.scheduling.builder import build_matches_for_stage_item
from bracket.logic.tournament_graph import TournamentGraph
from bracket.models.db.match import MatchBody
from bracket.models.db.stage_item import StageItem, StageItemWithInputsCreate
from bracket.models.db.stage_item_inputs import (
    StageItemInputCreateBody,
    StageItemInputCreateBodyFinal,
    StageItemInputCreateBodyTentative,
    StageItemInputFinal,
)
from bracket.models.enums import StageType, UserAccountType, UserXClubRelation
from bracket.sql.matches import sql_update_match
from bracket.sql.players import insert_players
from bracket.sql.stage_items import sql_create_stage_item_with_inputs
from bracket.sql.stages import get_full_tournament_details
from bracket.sql.teams import sql_add_team_players, sql_create_team
from bracket.sql.users import get_user
from bracket.utils.alembic import alembic_stamp_head
from bracket.utils.id_types import ClubId, StageId, TeamId, TournamentId, UserId
from bracket.utils.logging import logger
from bracket.utils.security import hash_password

# The account the example event belongs to, unless ADMIN_EMAIL names another one.
DEMO_USER_EMAIL = "admin@example.com"
DEMO_USER_PASSWORD = "adminadmin"
DEMO_START_TIME = datetime(2022, 1, 11, 4, 32, 11, tzinfo=UTC)
TEAMS = 8
PLAYERS_PER_TEAM = 2


async def add_demo_user(session: AsyncSession) -> UserId:
    existing = await get_user(session, DEMO_USER_EMAIL)
    if existing is not None:
        return existing.id

    user = orm.User(
        email=DEMO_USER_EMAIL,
        name="Admin",
        password_hash=hash_password(DEMO_USER_PASSWORD),
        account_type=UserAccountType.REGULAR,
    )
    session.add(user)
    await session.flush()
    return UserId(user.id)


async def add_event(session: AsyncSession, demo_user_id: UserId, admin_id: UserId | None) -> ClubId:
    """The example event. A configured administrator owns it, with the demo user helping."""
    club = orm.Club(name="Some Cool Club")
    session.add(club)
    await session.flush()

    admin_owns = admin_id is not None and admin_id != demo_user_id
    session.add(
        orm.UserXClub(
            club_id=club.id,
            user_id=demo_user_id,
            relation=UserXClubRelation.COLLABORATOR if admin_owns else UserXClubRelation.OWNER,
        )
    )
    if admin_owns:
        session.add(
            orm.UserXClub(club_id=club.id, user_id=admin_id, relation=UserXClubRelation.OWNER)
        )
    await session.flush()
    return ClubId(club.id)


async def add_tournament(
    session: AsyncSession, club_id: ClubId
) -> tuple[TournamentId, StageId, StageId]:
    """The tournament with its ranking, a group stage that is active and a knockout stage."""
    tournament = orm.Tournament(
        club_id=club_id,
        name="Some Cool Tournament",
        start_time=DEMO_START_TIME,
        dashboard_public=True,
        dashboard_endpoint="endpoint-test",
        players_can_be_in_multiple_teams=True,
        duration_minutes=10,
        margin_minutes=5,
    )
    session.add(tournament)
    await session.flush()

    groups = orm.Stage(tournament_id=tournament.id, name="Group Stage", is_active=True)
    knockout = orm.Stage(tournament_id=tournament.id, name="Knockout Stage", is_active=False)
    ranking = orm.Ranking(
        tournament_id=tournament.id,
        position=0,
        win_points=Decimal("1.0"),
        draw_points=Decimal("0.5"),
        loss_points=Decimal("0.0"),
        add_score_points=False,
    )
    session.add_all([groups, knockout, ranking])
    await session.flush()
    return TournamentId(tournament.id), StageId(groups.id), StageId(knockout.id)


async def add_teams(session: AsyncSession, tournament_id: TournamentId) -> list[TeamId]:
    team_ids = []
    for team_number in range(1, TEAMS + 1):
        team_id = await sql_create_team(session, tournament_id, f"Team {team_number}", True)
        first_player = (team_number - 1) * PLAYERS_PER_TEAM + 1
        player_ids = await insert_players(
            session,
            tournament_id,
            [
                f"Player {number:02d}"
                for number in range(first_player, first_player + PLAYERS_PER_TEAM)
            ],
            active=True,
        )
        await sql_add_team_players(session, tournament_id, team_id, player_ids)
        team_ids.append(team_id)
    return team_ids


async def add_stage_item(
    session: AsyncSession,
    tournament_id: TournamentId,
    stage_id: StageId,
    name: str,
    stage_type: StageType,
    inputs: list[StageItemInputCreateBody],
) -> StageItem:
    stage_item = await sql_create_stage_item_with_inputs(
        session,
        tournament_id,
        StageItemWithInputsCreate(
            stage_id=stage_id, name=name, type=stage_type, team_count=len(inputs), inputs=inputs
        ),
    )
    await build_matches_for_stage_item(session, stage_item, tournament_id)
    return stage_item


async def play_group_matches(session: AsyncSession, tournament_id: TournamentId) -> None:
    """Give every match whose teams are known a random result, and rank the stage items."""
    graph = TournamentGraph(await get_full_tournament_details(session, tournament_id))
    for match in graph.matches():
        if isinstance(match.stage_item_input1, StageItemInputFinal) and isinstance(
            match.stage_item_input2, StageItemInputFinal
        ):
            result = MatchBody(
                stage_item_input1_score=random.randint(0, 10),
                stage_item_input2_score=random.randint(0, 10),
            )
            await sql_update_match(session, match.id, result)
            graph.update_match(match.id, **result.model_dump())
    for stage_item in graph.stage_items():
        await recalculate_ranking_for_stage_item(session, tournament_id, stage_item)


async def create_dev_db(session: AsyncSession) -> UserId:
    """Replace every table with the example data. Returns the demo user's id."""
    if environment is not Environment.DEVELOPMENT:
        raise RuntimeError("Creating a development database requires ENVIRONMENT=DEVELOPMENT")

    logger.warning("Initializing database with dummy records")
    connection = await session.connection()
    await connection.run_sync(orm.Base.metadata.drop_all)
    await connection.run_sync(orm.Base.metadata.create_all)
    session.expunge_all()
    admin_id = await init_db_when_empty(connection)
    await connection.run_sync(alembic_stamp_head)

    demo_user_id = await add_demo_user(session)
    club_id = await add_event(session, demo_user_id, admin_id)
    tournament_id, groups_id, knockout_id = await add_tournament(session, club_id)
    team_ids = await add_teams(session, tournament_id)

    group_items = [
        await add_stage_item(
            session,
            tournament_id,
            groups_id,
            name,
            StageType.ROUND_ROBIN,
            [
                StageItemInputCreateBodyFinal(slot=slot, team_id=team_id)
                for slot, team_id in enumerate(group_teams, start=1)
            ],
        )
        for name, group_teams in (("Group A", team_ids[:4]), ("Group B", team_ids[4:]))
    ]
    await add_stage_item(
        session,
        tournament_id,
        knockout_id,
        "Bracket A",
        StageType.SINGLE_ELIMINATION,
        [
            StageItemInputCreateBodyTentative(
                slot=slot, winner_from_stage_item_id=group.id, winner_position=position
            )
            for slot, (group, position) in enumerate(
                ((group, position) for group in group_items for position in (1, 2)), start=1
            )
        ],
    )

    await play_group_matches(session, tournament_id)
    await schedule_all_matches(session, tournament_id)
    return demo_user_id
