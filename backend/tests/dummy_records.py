from decimal import Decimal
from zoneinfo import ZoneInfo

from heliclockter import datetime_utc

from bracket.models.db.match import MatchInsertable
from bracket.models.db.participation import TournamentTeam
from bracket.models.db.player import PlayerInsertable
from bracket.models.db.ranking import RankingInsertable
from bracket.models.db.round import RoundInsertable
from bracket.models.db.stage import StageInsertable
from bracket.models.db.stage_item import StageItemInsertable
from bracket.models.db.team import TeamInsertable
from bracket.models.db.tournament import TournamentInsertable
from bracket.models.db.user import UserInsertable
from bracket.models.enums import StageType, UserAccountType
from bracket.utils.id_types import (
    RankingId,
    RoundId,
    StageId,
    StageItemId,
    StageItemInputId,
    TeamId,
    TournamentId,
)
from bracket.utils.security import hash_password

DUMMY_MOCK_TIME = datetime_utc(2022, 1, 11, 4, 32, 11, tzinfo=ZoneInfo("UTC"))

# We don't know any db IDs here, so we use a placeholder for foreign keys.
DB_PLACEHOLDER_ID = -42

DUMMY_TOURNAMENT = TournamentInsertable(
    name="Some Cool Tournament",
    created=DUMMY_MOCK_TIME,
    start_time=DUMMY_MOCK_TIME,
    dashboard_public=True,
    dashboard_endpoint="endpoint-test",
    logo_path=None,
    duration_minutes=10,
    margin_minutes=5,
)

DUMMY_STAGE1 = StageInsertable(
    tournament_id=TournamentId(DB_PLACEHOLDER_ID),
    created=DUMMY_MOCK_TIME,
    is_active=True,
    name="Group Stage",
)

DUMMY_STAGE2 = StageInsertable(
    tournament_id=TournamentId(DB_PLACEHOLDER_ID),
    created=DUMMY_MOCK_TIME,
    is_active=False,
    name="Knockout Stage",
)

DUMMY_STAGE_ITEM1 = StageItemInsertable(
    stage_id=StageId(DB_PLACEHOLDER_ID),
    ranking_id=RankingId(DB_PLACEHOLDER_ID),
    created=DUMMY_MOCK_TIME,
    type=StageType.ROUND_ROBIN,
    team_count=4,
    name="Group A",
)

DUMMY_STAGE_ITEM2 = StageItemInsertable(
    stage_id=StageId(DB_PLACEHOLDER_ID),
    ranking_id=RankingId(DB_PLACEHOLDER_ID),
    created=DUMMY_MOCK_TIME,
    type=StageType.ROUND_ROBIN,
    team_count=4,
    name="Group B",
)

DUMMY_STAGE_ITEM3 = StageItemInsertable(
    stage_id=StageId(DB_PLACEHOLDER_ID),
    ranking_id=RankingId(DB_PLACEHOLDER_ID),
    created=DUMMY_MOCK_TIME,
    type=StageType.SINGLE_ELIMINATION,
    team_count=4,
    name="Bracket A",
)

DUMMY_ROUND1 = RoundInsertable(
    stage_item_id=StageItemId(DB_PLACEHOLDER_ID),
    created=DUMMY_MOCK_TIME,
    is_draft=False,
    name="Round 1",
)

DUMMY_ROUND2 = RoundInsertable(
    stage_item_id=StageItemId(DB_PLACEHOLDER_ID),
    created=DUMMY_MOCK_TIME,
    is_draft=True,
    name="Round 2",
)

DUMMY_ROUND3 = RoundInsertable(
    stage_item_id=StageItemId(DB_PLACEHOLDER_ID),
    created=DUMMY_MOCK_TIME,
    is_draft=False,
    name="Round 3",
)

DUMMY_MATCH1 = MatchInsertable(
    created=DUMMY_MOCK_TIME,
    start_time=DUMMY_MOCK_TIME,
    round_id=RoundId(DB_PLACEHOLDER_ID),
    stage_item_input1_id=StageItemInputId(DB_PLACEHOLDER_ID),
    stage_item_input2_id=StageItemInputId(DB_PLACEHOLDER_ID),
    stage_item_input1_score=11,
    stage_item_input2_score=22,
    stage_item_input1_winner_from_match_id=None,
    stage_item_input2_winner_from_match_id=None,
    duration_minutes=10,
    margin_minutes=5,
    custom_duration_minutes=None,
    custom_margin_minutes=None,
)

DUMMY_USER = UserInsertable(
    email="admin@example.com",
    name="Admin",
    password_hash=hash_password("adminadmin"),
    created=DUMMY_MOCK_TIME,
    account_type=UserAccountType.REGULAR,
)

DUMMY_TEAM1 = TeamInsertable(
    created=DUMMY_MOCK_TIME,
    name="Team 1",
)

DUMMY_TEAM2 = TeamInsertable(
    created=DUMMY_MOCK_TIME,
    name="Team 2",
)

DUMMY_TEAM3 = TeamInsertable(
    created=DUMMY_MOCK_TIME,
    name="Team 3",
)

DUMMY_TEAM4 = TeamInsertable(
    created=DUMMY_MOCK_TIME,
    name="Team 4",
)


DUMMY_PLAYER1 = PlayerInsertable(
    name="Player 01",
    created=DUMMY_MOCK_TIME,
)

DUMMY_PLAYER2 = PlayerInsertable(
    name="Player 02",
    created=DUMMY_MOCK_TIME,
)

DUMMY_PLAYER3 = PlayerInsertable(
    name="Player 03",
    created=DUMMY_MOCK_TIME,
)

DUMMY_PLAYER4 = PlayerInsertable(
    name="Player 04",
    created=DUMMY_MOCK_TIME,
)

DUMMY_PLAYER5 = PlayerInsertable(
    name="Player 05",
    created=DUMMY_MOCK_TIME,
)

DUMMY_PLAYER6 = PlayerInsertable(
    name="Player 06",
    created=DUMMY_MOCK_TIME,
)

DUMMY_PLAYER7 = PlayerInsertable(
    name="Player 07",
    created=DUMMY_MOCK_TIME,
)

DUMMY_PLAYER8 = PlayerInsertable(
    name="Player 08",
    created=DUMMY_MOCK_TIME,
)

DUMMY_RANKING1 = RankingInsertable(
    tournament_id=TournamentId(DB_PLACEHOLDER_ID),
    win_points=Decimal("1.0"),
    draw_points=Decimal("0.5"),
    loss_points=Decimal("0.0"),
    add_score_points=False,
    position=0,
)


def tournament_team(
    team: TeamInsertable,
    team_id: int,
    *,
    tournament_id: int = DB_PLACEHOLDER_ID,
    active: bool = True,
) -> TournamentTeam:
    """A team as it takes part in a tournament, for tests that build a stage tree by hand."""
    return TournamentTeam(
        **team.model_dump(),
        id=TeamId(team_id),
        tournament_id=TournamentId(tournament_id),
        active=active,
    )
