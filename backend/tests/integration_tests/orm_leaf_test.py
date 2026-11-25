from collections.abc import AsyncIterator
from dataclasses import dataclass
from datetime import datetime, timedelta
from decimal import Decimal
from typing import Literal

import pytest
import pytest_asyncio
from heliclockter import datetime_utc
from sqlalchemy.ext.asyncio import AsyncSession

from bracket import orm
from bracket.database import engine
from bracket.logic.participation import get_tournament_teams_with_totals
from bracket.logic.ranking.players import get_players_with_statistics
from bracket.models.db.team import TeamMemberBody
from bracket.models.db.tournament import Tournament
from bracket.models.enums import StageType, TournamentRole, TournamentStatus, UserAccountType
from bracket.sql.organizers import get_organized_tournament_ids
from bracket.sql.participation import (
    LineupScope,
    get_lineups,
    get_tournament_players,
    get_tournament_teams,
    sync_lineups,
)
from bracket.sql.teams import sql_replace_team_members
from bracket.sql.tournaments import (
    count_tournament_records,
    sql_get_tournament,
    sql_get_tournament_by_endpoint_name,
    sql_get_visible_tournaments,
)
from bracket.utils.id_types import PlayerId, TeamId, TournamentId, UserId
from bracket.utils.pagination import RESULT_SORT_FIELDS, PlayerPagination, TeamPagination

pytestmark = pytest.mark.asyncio(loop_scope="session")

TeamSortBy = Literal[
    "name", "elo_score", "swiss_score", "wins", "draws", "losses", "active", "created"
]
PlayerSortBy = Literal["name", "elo_score", "swiss_score", "wins", "draws", "losses", "created"]
TEAM_SORT_COLUMNS: tuple[TeamSortBy, ...] = (
    "name",
    "elo_score",
    "swiss_score",
    "wins",
    "draws",
    "losses",
    "active",
    "created",
)
STORED_PLAYER_SORT_COLUMNS: tuple[PlayerSortBy, ...] = ("name", "created")
DAY = datetime_utc.fromisoformat("2026-01-01T00:00:00Z")


@dataclass
class LeafData:
    """
    Tournaments that one organizer runs, and a foreign one. In the main one, Alpha (Zed and Amy)
    and Beta (Max) play, and Zulu takes part without players and isn't active. Free plays nowhere.
    Alpha also played in an archived tournament.
    """

    session: AsyncSession
    organizer_id: UserId
    tournaments: dict[str, orm.Tournament]
    players: dict[str, orm.Player]
    teams: dict[str, orm.Team]
    active_teams: set[str]

    @property
    def tournament_id(self) -> TournamentId:
        return TournamentId(self.tournaments["main"].id)

    def team_id(self, name: str) -> TeamId:
        return TeamId(self.teams[name].id)


@pytest_asyncio.fixture(loop_scope="session")
async def leaf_data() -> AsyncIterator[LeafData]:
    async with AsyncSession(engine, expire_on_commit=False) as session:
        organizer = orm.User(
            email="leaf-organizer@example.org",
            name="Organizer",
            password_hash="hash",
            account_type=UserAccountType.REGULAR,
        )
        tournaments = {
            name: orm.Tournament(
                name=name,
                start_time=DAY + timedelta(days=index),
                dashboard_public=public,
                dashboard_endpoint=f"orm-leaf-{name}",
                status=status,
            )
            for index, (name, status, public) in enumerate(
                [
                    ("main", TournamentStatus.OPEN, True),
                    ("empty", TournamentStatus.OPEN, False),
                    ("archived_public", TournamentStatus.ARCHIVED, True),
                    ("archived_private", TournamentStatus.ARCHIVED, False),
                    ("foreign", TournamentStatus.ARCHIVED, False),
                ]
            )
        }
        players = {
            name: orm.Player(name=name, created=DAY + timedelta(minutes=3 - index))
            for index, name in enumerate(["Zed", "Amy", "Max", "Free", "Foreign"])
        }
        teams = {
            name: orm.Team(name=name, created=DAY + timedelta(minutes=2 - index))
            for index, name in enumerate(["Alpha", "Zulu", "Beta", "Foreign"])
        }
        session.add_all([organizer, *tournaments.values(), *players.values(), *teams.values()])
        await session.flush()
        tournament_id = tournaments["main"].id
        session.add_all(
            orm.TournamentOrganizer(
                tournament_id=tournament.id, user_id=organizer.id, role=TournamentRole.OWNER
            )
            for name, tournament in tournaments.items()
            if name != "foreign"
        )
        session.add_all(
            orm.TeamMember(team_id=teams[team].id, player_id=players[player].id)
            for team, player in [
                ("Alpha", "Zed"),
                ("Alpha", "Amy"),
                ("Beta", "Max"),
                ("Foreign", "Foreign"),
            ]
        )
        active_teams = {"Alpha", "Beta"}
        session.add_all(
            orm.TournamentTeam(
                tournament_id=tournaments[tournament].id,
                team_id=teams[team].id,
                active=team in active_teams or tournament != "main",
            )
            for tournament, team in [
                ("main", "Alpha"),
                ("main", "Zulu"),
                ("main", "Beta"),
                ("archived_public", "Alpha"),
                ("foreign", "Foreign"),
            ]
        )
        await session.flush()
        session.add_all(
            orm.TournamentPlayer(
                tournament_id=tournaments[tournament].id,
                team_id=teams[team].id,
                player_id=players[player].id,
            )
            for tournament, team, player in [
                ("main", "Alpha", "Zed"),
                ("main", "Alpha", "Amy"),
                ("main", "Beta", "Max"),
                ("archived_public", "Alpha", "Zed"),
                ("archived_public", "Alpha", "Amy"),
                ("foreign", "Foreign", "Foreign"),
            ]
        )
        ranking = orm.Ranking(
            tournament_id=tournament_id,
            position=0,
            win_points=3,
            draw_points=1,
            loss_points=0,
            add_score_points=False,
        )
        stage = orm.Stage(tournament_id=tournament_id, name="Swiss", is_active=True)
        session.add_all([ranking, stage])
        await session.flush()
        item = orm.StageItem(
            tournament_id=tournament_id,
            stage_id=stage.id,
            ranking_id=ranking.id,
            name="Swiss",
            team_count=3,
            type=StageType.SWISS,
        )
        session.add(item)
        await session.flush()
        inputs = [
            orm.StageItemInput(
                stage_item_id=item.id,
                tournament_id=tournament_id,
                team_id=teams[team].id,
                slot=index,
            )
            for index, team in enumerate(["Alpha", "Zulu", "Beta"], start=1)
        ]
        published = orm.Round(
            tournament_id=tournament_id, stage_item_id=item.id, name="Published", is_draft=False
        )
        draft = orm.Round(
            tournament_id=tournament_id, stage_item_id=item.id, name="Draft", is_draft=True
        )
        session.add_all([*inputs, published, draft])
        await session.flush()
        session.add_all(
            [
                orm.Match(
                    tournament_id=tournament_id,
                    round_id=published.id,
                    stage_item_input1_id=inputs[0].id,
                    stage_item_input2_id=inputs[2].id,
                    stage_item_input1_score=3,
                    stage_item_input2_score=1,
                    start_time=DAY,
                    duration_minutes=60,
                    margin_minutes=10,
                ),
                orm.Match(
                    tournament_id=tournament_id,
                    round_id=published.id,
                    stage_item_input1_id=inputs[2].id,
                    stage_item_input2_id=inputs[1].id,
                    stage_item_input1_score=0,
                    stage_item_input2_score=0,
                    scoreless_result=True,
                    start_time=DAY + timedelta(hours=1),
                    duration_minutes=5,
                    margin_minutes=5,
                ),
                orm.Match(
                    tournament_id=tournament_id,
                    round_id=published.id,
                    stage_item_input1_score=0,
                    stage_item_input2_score=0,
                    duration_minutes=10,
                    margin_minutes=0,
                ),
                orm.Match(
                    tournament_id=tournament_id,
                    round_id=draft.id,
                    stage_item_input1_id=inputs[1].id,
                    stage_item_input2_id=inputs[0].id,
                    stage_item_input1_score=99,
                    stage_item_input2_score=0,
                    start_time=DAY + timedelta(days=30),
                    duration_minutes=10,
                    margin_minutes=0,
                ),
            ]
        )
        await session.flush()
        try:
            yield LeafData(session, UserId(organizer.id), tournaments, players, teams, active_teams)
        finally:
            await session.rollback()


LINEUP = ("Zed", "Amy", "Max")


@pytest.mark.parametrize("sort_by", STORED_PLAYER_SORT_COLUMNS)
@pytest.mark.parametrize("direction", ["asc", "desc"])
async def test_player_order_and_pagination(
    leaf_data: LeafData, sort_by: PlayerSortBy, direction: Literal["asc", "desc"]
) -> None:
    expected = sorted(
        (leaf_data.players[name] for name in LINEUP),
        key=lambda player: getattr(player, sort_by),
        reverse=direction == "desc",
    )
    actual = await get_tournament_players(
        leaf_data.session,
        leaf_data.tournament_id,
        pagination=PlayerPagination(limit=2, offset=1, sort_by=sort_by, sort_direction=direction),
    )
    assert [player.id for player in actual] == [player.id for player in expected[1:3]]


@pytest.mark.parametrize("sort_by", sorted(RESULT_SORT_FIELDS))
@pytest.mark.parametrize("direction", ["asc", "desc"])
async def test_player_results_are_sorted_before_the_page_is_cut(
    leaf_data: LeafData, sort_by: PlayerSortBy, direction: Literal["asc", "desc"]
) -> None:
    everyone = await get_players_with_statistics(leaf_data.session, leaf_data.tournament_id)
    expected = sorted(everyone, key=lambda player: player.id)
    expected.sort(key=lambda player: getattr(player, sort_by), reverse=direction == "desc")
    actual = await get_players_with_statistics(
        leaf_data.session,
        leaf_data.tournament_id,
        pagination=PlayerPagination(limit=2, offset=1, sort_by=sort_by, sort_direction=direction),
    )
    assert [player.id for player in actual] == [player.id for player in expected[1:3]]


async def test_the_lineup_and_its_count(leaf_data: LeafData) -> None:
    players = await get_tournament_players(leaf_data.session, leaf_data.tournament_id)
    assert [(player.name, player.team_id) for player in players] == [
        ("Amy", leaf_data.team_id("Alpha")),
        ("Max", leaf_data.team_id("Beta")),
        ("Zed", leaf_data.team_id("Alpha")),
    ]
    assert (
        await count_tournament_records(
            leaf_data.session, orm.TournamentPlayer, leaf_data.tournament_id
        )
        == 3
    )
    assert (
        await get_tournament_players(
            leaf_data.session,
            leaf_data.tournament_id,
            pagination=PlayerPagination(limit=2, offset=10),
        )
        == []
    )


@pytest.mark.parametrize("sort_by", TEAM_SORT_COLUMNS)
@pytest.mark.parametrize("direction", ["asc", "desc"])
async def test_team_order_totals_and_pagination(
    leaf_data: LeafData, sort_by: TeamSortBy, direction: Literal["asc", "desc"]
) -> None:
    expected_totals: dict[str, dict[str, Decimal | int]] = {
        "Alpha": {
            "elo_score": Decimal("1216"),
            "swiss_score": Decimal("1"),
            "wins": 1,
            "draws": 0,
            "losses": 0,
        },
        "Beta": {
            "elo_score": Decimal("1185"),
            "swiss_score": Decimal("0.5"),
            "wins": 0,
            "draws": 1,
            "losses": 1,
        },
        "Zulu": {
            "elo_score": Decimal("1199"),
            "swiss_score": Decimal("0.5"),
            "wins": 0,
            "draws": 1,
            "losses": 0,
        },
    }

    def sort_key(team: orm.Team) -> Decimal | int | str | datetime:
        if sort_by in expected_totals[team.name]:
            return expected_totals[team.name][sort_by]
        if sort_by == "active":
            return team.name in leaf_data.active_teams
        return team.created if sort_by == "created" else team.name

    # SQL sorting by a stored field and Python sorting by replayed totals both start in name order.
    expected = sorted(
        (leaf_data.teams[name] for name in expected_totals), key=lambda team: team.name
    )
    expected.sort(key=sort_key, reverse=direction == "desc")
    actual = await get_tournament_teams_with_totals(
        leaf_data.session,
        leaf_data.tournament_id,
        pagination=TeamPagination(limit=2, offset=1, sort_by=sort_by, sort_direction=direction),
    )
    assert [team.id for team in actual] == [team.id for team in expected[1:3]]
    for team in actual:
        assert {key: getattr(team, key) for key in expected_totals[team.name]} == expected_totals[
            team.name
        ]


async def test_tournament_teams_with_their_lineups(leaf_data: LeafData) -> None:
    teams = await get_tournament_teams(leaf_data.session, leaf_data.tournament_id)
    assert [(team.name, team.active) for team in teams] == [
        ("Alpha", True),
        ("Beta", True),
        ("Zulu", False),
    ]
    assert {team.name: [player.name for player in team.players] for team in teams} == {
        "Alpha": ["Amy", "Zed"],
        "Zulu": [],
        "Beta": ["Max"],
    }
    # With their results, the best first.
    ranked = await get_tournament_teams_with_totals(leaf_data.session, leaf_data.tournament_id)
    assert [team.name for team in ranked] == ["Alpha", "Zulu", "Beta"]
    assert (
        await get_tournament_teams(leaf_data.session, leaf_data.tournament_id, team_id=TeamId(-1))
        == []
    )


async def test_open_lineups_follow_a_roster_and_archived_ones_keep_theirs(
    leaf_data: LeafData,
) -> None:
    """Who played in an archived tournament stays as it was when the team's roster changes."""
    alpha_id = leaf_data.team_id("Alpha")
    free_id = PlayerId(leaf_data.players["Free"].id)
    amy_id = PlayerId(leaf_data.players["Amy"].id)
    zed_id = PlayerId(leaf_data.players["Zed"].id)

    await sql_replace_team_members(
        leaf_data.session,
        alpha_id,
        [TeamMemberBody(player_id=free_id), TeamMemberBody(player_id=zed_id, active=False)],
    )
    await sync_lineups(leaf_data.session, LineupScope.of_teams({alpha_id}))

    assert (await get_lineups(leaf_data.session, leaf_data.tournament_id))[alpha_id] == {free_id}
    archived = TournamentId(leaf_data.tournaments["archived_public"].id)
    assert (await get_lineups(leaf_data.session, archived))[alpha_id] == {amy_id, zed_id}


async def test_tournament_progress_all_loaders(leaf_data: LeafData) -> None:
    session = leaf_data.session
    main = await sql_get_tournament(session, leaf_data.tournament_id)
    assert (main.matches_total, main.matches_played, main.last_match_end) == (
        3,
        2,
        DAY + timedelta(minutes=70),
    )
    assert main.more_rounds_possible is True
    endpoint = await sql_get_tournament_by_endpoint_name(session, "ORM-LEAF-MAIN")
    assert endpoint == main
    assert await sql_get_tournament_by_endpoint_name(session, "orm-leaf-empty") is None
    assert await sql_get_tournament_by_endpoint_name(session, "missing") is None
    # Other tests' tournaments can be visible too: these only look at the fixture's.
    fixture_ids = {tournament.id for tournament in leaf_data.tournaments.values()}

    def fixture(tournaments: list[Tournament]) -> list[Tournament]:
        return [tournament for tournament in tournaments if tournament.id in fixture_ids]

    owned = fixture(
        await sql_get_visible_tournaments(session, leaf_data.organizer_id, filter_="ALL")
    )
    assert [tournament.name for tournament in owned] == [
        "empty",
        "main",
        "archived_private",
        "archived_public",
    ]
    assert next(tournament for tournament in owned if tournament.name == "main") == main
    for tournament in owned:
        if tournament.name != "main":
            assert (
                tournament.matches_total,
                tournament.matches_played,
                tournament.last_match_end,
                tournament.more_rounds_possible,
            ) == (0, 0, None, False)
    assert [
        tournament.name
        for tournament in fixture(
            await sql_get_visible_tournaments(session, leaf_data.organizer_id, filter_="ARCHIVED")
        )
    ] == ["archived_private", "archived_public"]
    assert await get_organized_tournament_ids(session, leaf_data.organizer_id) == {
        tournament.id for name, tournament in leaf_data.tournaments.items() if name != "foreign"
    }

    public = fixture(await sql_get_visible_tournaments(session, None, filter_="ALL"))
    assert [tournament.name for tournament in public] == ["empty", "main", "archived_public"]
    assert next(tournament for tournament in public if tournament.name == "main") == main
    assert [
        tournament.name for tournament in fixture(await sql_get_visible_tournaments(session, None))
    ] == ["empty", "main"]
