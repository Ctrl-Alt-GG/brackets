from collections.abc import AsyncIterator
from dataclasses import dataclass
from datetime import timedelta
from decimal import Decimal
from typing import Literal

import pytest
import pytest_asyncio
from heliclockter import datetime_utc
from sqlalchemy.ext.asyncio import AsyncSession

from bracket import orm
from bracket.database import engine
from bracket.models.db.stage_item import StageType
from bracket.models.db.tournament import TournamentStatus
from bracket.sql.players import get_all_players_in_tournament, get_player_count
from bracket.sql.teams import get_team_count, get_teams_with_members, sql_set_team_members
from bracket.sql.tournaments import (
    sql_get_tournament,
    sql_get_tournament_by_endpoint_name,
    sql_get_tournaments,
    sql_get_visible_tournaments,
)
from bracket.utils.id_types import ClubId, PlayerId, TeamId, TournamentId
from bracket.utils.pagination import PaginationPlayers, PaginationTeams

pytestmark = pytest.mark.asyncio(loop_scope="session")

SortBy = Literal["name", "elo_score", "swiss_score", "wins", "draws", "losses", "active", "created"]
SORT_COLUMNS: tuple[SortBy, ...] = (
    "name",
    "elo_score",
    "swiss_score",
    "wins",
    "draws",
    "losses",
    "active",
    "created",
)
DAY = datetime_utc.fromisoformat("2026-01-01T00:00:00Z")


@dataclass
class LeafData:
    session: AsyncSession
    club_id: ClubId
    tournaments: dict[str, orm.Tournament]
    players: list[orm.Player]
    teams: list[orm.Team]

    @property
    def tournament_id(self) -> TournamentId:
        return TournamentId(self.tournaments["main"].id)


@pytest_asyncio.fixture(loop_scope="session")
async def leaf_data() -> AsyncIterator[LeafData]:
    async with AsyncSession(engine, expire_on_commit=False) as session:
        club = orm.Club(name="Repository fixtures")
        other_club = orm.Club(name="Other repository fixtures")
        session.add_all([club, other_club])
        await session.flush()
        tournaments = {
            name: orm.Tournament(
                name=name,
                club_id=other_club.id if name == "foreign" else club.id,
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
        session.add_all(tournaments.values())
        await session.flush()
        tournament_id = tournaments["main"].id
        players = [
            orm.Player(
                tournament_id=tournament_id,
                name=name,
                active=index != 1,
                created=DAY + timedelta(minutes=3 - index),
                elo_score=float(1000 + index),
                swiss_score=float(3 - index),
                wins=index,
                draws=3 - index,
                losses=(index + 2) % 4,
            )
            for index, name in enumerate(["Zed", "Amy", "Max", "Free"])
        ]
        teams = [
            orm.Team(
                tournament_id=tournament_id,
                name=name,
                active=index != 1,
                created=DAY + timedelta(minutes=2 - index),
            )
            for index, name in enumerate(["Alpha", "Zulu", "Beta"])
        ]
        ranking = orm.Ranking(
            tournament_id=tournament_id,
            position=0,
            win_points=3,
            draw_points=1,
            loss_points=0,
            add_score_points=False,
        )
        stage = orm.Stage(tournament_id=tournament_id, name="Swiss", is_active=True)
        session.add_all([*players, *teams, ranking, stage])
        await session.flush()
        session.add_all(
            [
                orm.PlayerXTeam(
                    tournament_id=tournament_id, team_id=teams[0].id, player_id=players[0].id
                ),
                orm.PlayerXTeam(
                    tournament_id=tournament_id, team_id=teams[0].id, player_id=players[1].id
                ),
                orm.PlayerXTeam(
                    tournament_id=tournament_id, team_id=teams[2].id, player_id=players[2].id
                ),
                orm.Player(
                    tournament_id=tournaments["foreign"].id,
                    name="Foreign",
                    elo_score=0,
                    swiss_score=0,
                    wins=0,
                    draws=0,
                    losses=0,
                ),
                orm.Team(tournament_id=tournaments["foreign"].id, name="Foreign"),
            ]
        )
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
                stage_item_id=item.id, tournament_id=tournament_id, team_id=team.id, slot=index
            )
            for index, team in enumerate(teams, start=1)
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
                    stage_item_input1_conflict=False,
                    stage_item_input2_conflict=False,
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
                    stage_item_input1_conflict=False,
                    stage_item_input2_conflict=False,
                    start_time=DAY + timedelta(hours=1),
                ),
                orm.Match(
                    tournament_id=tournament_id,
                    round_id=published.id,
                    stage_item_input1_score=0,
                    stage_item_input2_score=0,
                    stage_item_input1_conflict=False,
                    stage_item_input2_conflict=False,
                ),
                orm.Match(
                    tournament_id=tournament_id,
                    round_id=draft.id,
                    stage_item_input1_id=inputs[1].id,
                    stage_item_input2_id=inputs[0].id,
                    stage_item_input1_score=99,
                    stage_item_input2_score=0,
                    stage_item_input1_conflict=False,
                    stage_item_input2_conflict=False,
                    start_time=DAY + timedelta(days=30),
                    duration_minutes=10,
                ),
            ]
        )
        await session.flush()
        try:
            yield LeafData(session, ClubId(club.id), tournaments, players, teams)
        finally:
            await session.rollback()


@pytest.mark.parametrize("sort_by", SORT_COLUMNS)
@pytest.mark.parametrize("direction", ["asc", "desc"])
async def test_player_order_and_pagination(
    leaf_data: LeafData, sort_by: SortBy, direction: Literal["asc", "desc"]
) -> None:
    expected = sorted(
        leaf_data.players, key=lambda player: getattr(player, sort_by), reverse=direction == "desc"
    )
    actual = await get_all_players_in_tournament(
        leaf_data.session,
        leaf_data.tournament_id,
        pagination=PaginationPlayers(limit=2, offset=1, sort_by=sort_by, sort_direction=direction),
    )
    assert [player.id for player in actual] == [player.id for player in expected[1:3]]


async def test_player_membership_filter_and_counts(leaf_data: LeafData) -> None:
    all_players = await get_all_players_in_tournament(leaf_data.session, leaf_data.tournament_id)
    assert [player.name for player in all_players] == ["Amy", "Free", "Max", "Zed"]
    free_players = await get_all_players_in_tournament(
        leaf_data.session,
        leaf_data.tournament_id,
        not_in_team=True,
        pagination=PaginationPlayers(limit=1, offset=0, sort_by="name", sort_direction="desc"),
    )
    assert [player.name for player in free_players] == ["Free"]
    assert await get_player_count(leaf_data.session, leaf_data.tournament_id) == 4
    assert await get_player_count(leaf_data.session, leaf_data.tournament_id, not_in_team=True) == 1
    assert (
        await get_all_players_in_tournament(
            leaf_data.session,
            leaf_data.tournament_id,
            pagination=PaginationPlayers(limit=2, offset=10),
        )
        == []
    )


@pytest.mark.parametrize("sort_by", SORT_COLUMNS)
@pytest.mark.parametrize("direction", ["asc", "desc"])
async def test_team_order_totals_and_pagination(
    leaf_data: LeafData, sort_by: SortBy, direction: Literal["asc", "desc"]
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
    # SQL sorting by a stored field and Python sorting by replayed totals both start in name order.
    expected = sorted(leaf_data.teams, key=lambda team: team.name)
    expected.sort(
        key=lambda team: (
            expected_totals[team.name][sort_by]
            if sort_by in expected_totals[team.name]
            else getattr(team, sort_by)
        ),
        reverse=direction == "desc",
    )
    actual = await get_teams_with_members(
        leaf_data.session,
        leaf_data.tournament_id,
        pagination=PaginationTeams(limit=2, offset=1, sort_by=sort_by, sort_direction=direction),
    )
    assert [team.id for team in actual] == [team.id for team in expected[1:3]]
    for team in actual:
        assert {key: getattr(team, key) for key in expected_totals[team.name]} == expected_totals[
            team.name
        ]


async def test_team_members_filters_and_refresh(leaf_data: LeafData) -> None:
    teams = await get_teams_with_members(leaf_data.session, leaf_data.tournament_id)
    assert [team.name for team in teams] == ["Alpha", "Zulu", "Beta"]
    assert {team.name: [player.name for player in team.players] for team in teams} == {
        "Alpha": ["Amy", "Zed"],
        "Zulu": [],
        "Beta": ["Max"],
    }
    active = await get_teams_with_members(
        leaf_data.session, leaf_data.tournament_id, only_active_teams=True
    )
    assert [team.name for team in active] == ["Alpha", "Beta"]
    assert await get_team_count(leaf_data.session, leaf_data.tournament_id) == 3
    assert (
        await get_team_count(leaf_data.session, leaf_data.tournament_id, only_active_teams=True)
        == 2
    )
    alpha_id = TeamId(leaf_data.teams[0].id)
    await sql_set_team_members(
        leaf_data.session,
        leaf_data.tournament_id,
        alpha_id,
        {PlayerId(leaf_data.players[3].id)},
        {PlayerId(leaf_data.players[0].id), PlayerId(leaf_data.players[1].id)},
    )
    [updated] = await get_teams_with_members(
        leaf_data.session, leaf_data.tournament_id, team_id=alpha_id
    )
    assert [player.name for player in updated.players] == ["Free"]
    assert (
        await get_teams_with_members(
            leaf_data.session,
            leaf_data.tournament_id,
            team_id=TeamId(-1),
            only_active_teams=True,
        )
        == []
    )


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
    owned = await sql_get_tournaments(session, [leaf_data.club_id])
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
        for tournament in await sql_get_tournaments(session, [leaf_data.club_id], filter_="OPEN")
    ] == ["empty", "main"]
    assert [
        tournament.name
        for tournament in await sql_get_tournaments(
            session, [leaf_data.club_id], filter_="ARCHIVED"
        )
    ] == ["archived_private", "archived_public"]
    assert await sql_get_tournaments(session, []) == []
    public = await sql_get_visible_tournaments(session, [], filter_="ALL")
    assert [tournament.name for tournament in public] == ["empty", "main", "archived_public"]
    assert next(tournament for tournament in public if tournament.name == "main") == main
    assert await sql_get_visible_tournaments(session, [leaf_data.club_id], filter_="ALL") == owned
    assert [tournament.name for tournament in await sql_get_visible_tournaments(session, [])] == [
        "empty",
        "main",
    ]
