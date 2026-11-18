from collections.abc import AsyncIterator
from dataclasses import dataclass
from decimal import Decimal
from typing import Any

import pytest
import pytest_asyncio
from heliclockter import datetime_utc
from pydantic import ValidationError
from sqlalchemy import delete, select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from bracket import orm
from bracket.database import engine
from bracket.models.db.ranking import RankingBody, RankingCreateBody
from bracket.models.enums import StageType, UserAccountType, UserXClubRelation
from bracket.sql.rankings import sql_create_ranking, sql_update_ranking
from bracket.sql.tournaments import sql_delete_tournament
from bracket.utils.id_types import RankingId, TournamentId

pytestmark = pytest.mark.asyncio(loop_scope="session")


@dataclass
class IntegrityData:
    session: AsyncSession
    club: orm.Club
    tournaments: list[orm.Tournament]
    stages: list[orm.Stage]
    rankings: list[orm.Ranking]
    items: list[orm.StageItem]
    rounds: list[orm.Round]
    teams: list[orm.Team]
    players: list[orm.Player]
    slots: list[orm.StageItemInput]
    matches: list[orm.Match]


def match_values(tournament_id: int, round_id: int, **values: Any) -> dict[str, Any]:
    return {
        "tournament_id": tournament_id,
        "round_id": round_id,
        "stage_item_input1_score": 0,
        "stage_item_input2_score": 0,
        "stage_item_input1_conflict": False,
        "stage_item_input2_conflict": False,
        "duration_minutes": 15,
        "margin_minutes": 5,
        **values,
    }


@pytest_asyncio.fixture(loop_scope="session")
async def integrity_data() -> AsyncIterator[IntegrityData]:
    async with AsyncSession(engine, expire_on_commit=False) as session:
        club = orm.Club(name="Integrity tests")
        session.add(club)
        await session.flush()
        tournaments = [
            orm.Tournament(
                club_id=club.id,
                name=f"Tournament {index}",
                start_time=datetime_utc.now(),
                dashboard_public=False,
            )
            for index in range(2)
        ]
        session.add_all(tournaments)
        await session.flush()
        stages = [orm.Stage(tournament_id=t.id, name="Groups") for t in tournaments]
        rankings = [
            orm.Ranking(
                tournament_id=t.id,
                position=0,
                win_points=Decimal("1"),
                draw_points=Decimal("0.5"),
                loss_points=Decimal("0"),
                add_score_points=False,
            )
            for t in tournaments
        ]
        teams = [orm.Team(tournament_id=t.id, name="Team") for t in tournaments]
        players = [
            orm.Player(
                tournament_id=t.id,
                name="Player",
                elo_score=1200,
                swiss_score=0,
                wins=0,
                draws=0,
                losses=0,
            )
            for t in tournaments
        ]
        session.add_all([*stages, *rankings, *teams, *players])
        await session.flush()
        items = [
            orm.StageItem(
                tournament_id=t.id,
                stage_id=s.id,
                ranking_id=r.id,
                name="Group",
                team_count=2,
                type=StageType.ROUND_ROBIN,
            )
            for t, s, r in zip(tournaments, stages, rankings, strict=True)
        ]
        session.add_all(items)
        await session.flush()
        rounds = [
            orm.Round(tournament_id=t.id, stage_item_id=i.id, name="Round", is_draft=False)
            for t, i in zip(tournaments, items, strict=True)
        ]
        slots = [
            orm.StageItemInput(tournament_id=t.id, stage_item_id=i.id, team_id=team.id, slot=1)
            for t, i, team in zip(tournaments, items, teams, strict=True)
        ]
        session.add_all([*rounds, *slots])
        await session.flush()
        matches = [
            orm.Match(**match_values(t.id, r.id)) for t, r in zip(tournaments, rounds, strict=True)
        ]
        session.add_all(matches)
        await session.flush()
        try:
            yield IntegrityData(
                session,
                club,
                tournaments,
                stages,
                rankings,
                items,
                rounds,
                teams,
                players,
                slots,
                matches,
            )
        finally:
            await session.rollback()


@pytest.mark.parametrize(
    ("kind", "constraint"),
    [
        ("stage", "stage_items_stage_id_fkey"),
        ("ranking", "stage_items_ranking_id_fkey"),
        ("round", "rounds_stage_item_id_fkey"),
        ("slot", "stage_item_inputs_stage_item_id_fkey"),
        ("team", "stage_item_inputs_team_id_fkey"),
        ("source_item", "stage_item_inputs_winner_from_stage_item_id_fkey"),
        ("match_round", "matches_round_id_fkey"),
        ("match_slot", "matches_stage_item_input1_id_fkey"),
        ("source_match", "matches_stage_item_input1_winner_from_match_id_fkey"),
        ("membership_player", "players_x_teams_player_id_fkey"),
        ("membership_team", "players_x_teams_team_id_fkey"),
    ],
)
async def test_database_rejects_cross_tournament_references(
    integrity_data: IntegrityData, kind: str, constraint: str
) -> None:
    d = integrity_data
    tournament_id = d.tournaments[0].id
    entities = {
        "stage": lambda: orm.StageItem(
            tournament_id=tournament_id,
            stage_id=d.stages[1].id,
            ranking_id=d.rankings[0].id,
            name="Invalid",
            team_count=2,
            type=StageType.ROUND_ROBIN,
        ),
        "ranking": lambda: orm.StageItem(
            tournament_id=tournament_id,
            stage_id=d.stages[0].id,
            ranking_id=d.rankings[1].id,
            name="Invalid",
            team_count=2,
            type=StageType.ROUND_ROBIN,
        ),
        "round": lambda: orm.Round(
            tournament_id=tournament_id,
            stage_item_id=d.items[1].id,
            name="Invalid",
            is_draft=False,
        ),
        "slot": lambda: orm.StageItemInput(
            tournament_id=tournament_id,
            stage_item_id=d.items[1].id,
            slot=2,
        ),
        "team": lambda: orm.StageItemInput(
            tournament_id=tournament_id,
            stage_item_id=d.items[0].id,
            team_id=d.teams[1].id,
            slot=2,
        ),
        "source_item": lambda: orm.StageItemInput(
            tournament_id=tournament_id,
            stage_item_id=d.items[0].id,
            slot=2,
            winner_from_stage_item_id=d.items[1].id,
            winner_position=1,
        ),
        "match_round": lambda: orm.Match(**match_values(tournament_id, d.rounds[1].id)),
        "match_slot": lambda: orm.Match(
            **match_values(
                tournament_id,
                d.rounds[0].id,
                stage_item_input1_id=d.slots[1].id,
            )
        ),
        "source_match": lambda: orm.Match(
            **match_values(
                tournament_id,
                d.rounds[0].id,
                stage_item_input1_winner_from_match_id=d.matches[1].id,
            )
        ),
        "membership_player": lambda: orm.PlayerXTeam(
            tournament_id=tournament_id,
            player_id=d.players[1].id,
            team_id=d.teams[0].id,
        ),
        "membership_team": lambda: orm.PlayerXTeam(
            tournament_id=tournament_id,
            player_id=d.players[0].id,
            team_id=d.teams[1].id,
        ),
    }
    with pytest.raises(IntegrityError, match=constraint):
        async with d.session.begin_nested():
            d.session.add(entities[kind]())
            await d.session.flush()


async def test_duplicate_slots_and_memberships_are_rejected(integrity_data: IntegrityData) -> None:
    d = integrity_data
    tournament_id = d.tournaments[0].id
    membership = dict(tournament_id=tournament_id, team_id=d.teams[0].id, player_id=d.players[0].id)
    d.session.add(orm.PlayerXTeam(**membership))
    await d.session.flush()
    for entity, constraint in [
        (orm.PlayerXTeam(**membership), "uq_players_x_teams_membership"),
        (
            orm.StageItemInput(tournament_id=tournament_id, stage_item_id=d.items[0].id, slot=1),
            "uq_stage_item_inputs_slot",
        ),
    ]:
        with pytest.raises(IntegrityError, match=constraint):
            async with d.session.begin_nested():
                d.session.add(entity)
                await d.session.flush()


async def test_only_one_owner_per_club(integrity_data: IntegrityData) -> None:
    d = integrity_data
    users = [
        orm.User(
            email=f"owner{index}@example.org",
            name="Owner",
            password_hash="hash",
            account_type=UserAccountType.REGULAR,
        )
        for index in range(2)
    ]
    d.session.add_all(users)
    await d.session.flush()
    d.session.add(
        orm.UserXClub(club_id=d.club.id, user_id=users[0].id, relation=UserXClubRelation.OWNER)
    )
    await d.session.flush()
    with pytest.raises(IntegrityError, match="uq_users_x_clubs_owner"):
        async with d.session.begin_nested():
            d.session.add(
                orm.UserXClub(
                    club_id=d.club.id, user_id=users[1].id, relation=UserXClubRelation.OWNER
                )
            )
            await d.session.flush()


@pytest.mark.parametrize(
    ("values", "constraint"),
    [
        ({"stage_item_input1_score": -1}, "ck_matches_scores"),
        ({"stage_item_input2_score": 100001}, "ck_matches_scores"),
        ({"duration_minutes": 0}, "ck_matches_duration"),
        ({"margin_minutes": -1}, "ck_matches_margin"),
        ({"custom_duration_minutes": 1441}, "ck_matches_custom_duration"),
        ({"custom_margin_minutes": -1}, "ck_matches_custom_margin"),
        ({"scoreless_result": True, "stage_item_input1_score": 1}, "ck_matches_scoreless_result"),
    ],
)
async def test_invalid_match_values_are_rejected(
    integrity_data: IntegrityData, values: dict[str, int | bool], constraint: str
) -> None:
    d = integrity_data
    with pytest.raises(IntegrityError, match=constraint):
        async with d.session.begin_nested():
            d.session.add(orm.Match(**match_values(d.tournaments[0].id, d.rounds[0].id, **values)))
            await d.session.flush()


async def test_ranking_and_slot_points_round_trip_exactly(integrity_data: IntegrityData) -> None:
    d = integrity_data
    body = RankingCreateBody(win_points=Decimal("0.123456"), draw_points=Decimal("0.000001"))
    await sql_create_ranking(d.session, TournamentId(d.tournaments[0].id), body, position=1)
    created = (await d.session.scalars(select(orm.Ranking).where(orm.Ranking.position == 1))).one()
    assert created.win_points == Decimal("0.123456")
    assert created.draw_points == Decimal("0.000001")
    update_body = RankingBody(
        win_points=Decimal("0.654321"),
        draw_points=Decimal("0.000002"),
        loss_points=Decimal("-0.123456"),
        add_score_points=False,
        position=1,
    )
    await sql_update_ranking(
        d.session, TournamentId(d.tournaments[0].id), RankingId(created.id), update_body
    )
    d.slots[0].points = Decimal("123456.654321")
    await d.session.flush()
    ranking_id, slot_id = created.id, d.slots[0].id
    d.session.expire_all()
    restored = await d.session.get(orm.Ranking, ranking_id)
    assert restored is not None
    assert (restored.win_points, restored.draw_points, restored.loss_points) == (
        Decimal("0.654321"),
        Decimal("0.000002"),
        Decimal("-0.123456"),
    )
    assert await d.session.scalar(
        select(orm.StageItemInput.points).where(orm.StageItemInput.id == slot_id)
    ) == Decimal("123456.654321")
    with pytest.raises(ValidationError, match="decimal_max_places"):
        RankingCreateBody(win_points=Decimal("0.1234567"))


async def test_clearing_winner_links_keeps_the_dependent_tournament(
    integrity_data: IntegrityData,
) -> None:
    d = integrity_data
    dependent = orm.Match(
        **match_values(
            d.tournaments[0].id,
            d.rounds[0].id,
            stage_item_input1_winner_from_match_id=d.matches[0].id,
        )
    )
    d.session.add(dependent)
    await d.session.flush()
    await d.session.execute(delete(orm.Match).where(orm.Match.id == d.matches[0].id))
    row = (
        await d.session.execute(
            select(orm.Match.tournament_id, orm.Match.stage_item_input1_winner_from_match_id).where(
                orm.Match.id == dependent.id
            )
        )
    ).one()
    assert row == (d.tournaments[0].id, None)


async def test_tournament_deletion_cascades_through_scoped_foreign_keys(
    integrity_data: IntegrityData,
) -> None:
    d = integrity_data
    d.session.add_all(
        orm.PlayerXTeam(tournament_id=t.id, team_id=team.id, player_id=player.id)
        for t, team, player in zip(d.tournaments, d.teams, d.players, strict=True)
    )
    await d.session.flush()
    opponent = orm.Team(tournament_id=d.tournaments[0].id, name="Opponent")
    d.session.add(opponent)
    await d.session.flush()
    opponent_slot = orm.StageItemInput(
        tournament_id=d.tournaments[0].id,
        stage_item_id=d.items[0].id,
        team_id=opponent.id,
        slot=2,
    )
    d.session.add(opponent_slot)
    await d.session.flush()
    await d.session.execute(
        update(orm.Match)
        .where(orm.Match.id == d.matches[0].id)
        .values(
            stage_item_input1_id=d.slots[0].id,
            stage_item_input2_id=opponent_slot.id,
            stage_item_input1_score=3,
            stage_item_input2_score=1,
        )
    )
    await sql_delete_tournament(d.session, TournamentId(d.tournaments[0].id))
    for entity in (
        orm.Stage,
        orm.StageItem,
        orm.Round,
        orm.Match,
        orm.StageItemInput,
        orm.PlayerXTeam,
        orm.Team,
        orm.Player,
        orm.Ranking,
    ):
        assert list(
            await d.session.scalars(
                select(entity.tournament_id).where(
                    entity.tournament_id.in_([tournament.id for tournament in d.tournaments])
                )
            )
        ) == [d.tournaments[1].id]
