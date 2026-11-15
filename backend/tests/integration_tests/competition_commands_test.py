from collections.abc import AsyncIterator
from dataclasses import dataclass
from decimal import Decimal
from itertools import combinations

import pytest
import pytest_asyncio
from fastapi import HTTPException
from sqlalchemy import event, select
from sqlalchemy.ext.asyncio import AsyncSession

from bracket import orm
from bracket.database import session_factory
from bracket.logic.scheduling.builder import build_matches_for_stage_item
from bracket.models.db.match import MatchCreateBodyFrontend
from bracket.models.db.round import RoundCreateBody
from bracket.models.db.stage_item import StageItem, StageItemCreateBody, StageType
from bracket.models.db.stage_item_inputs import (
    StageItemInputUpdateBodyFinal,
    StageItemInputUpdateBodyTentative,
)
from bracket.sql.stage_item_inputs import get_stage_item_input_by_id
from bracket.sql.stage_items import sql_create_stage_item_with_empty_inputs
from bracket.sql.validation import (
    validate_match_create,
    validate_player_ids,
    validate_round_create,
    validate_stage_item_create,
    validate_stage_item_input_update,
)
from bracket.utils.dummy_records import DUMMY_MOCK_TIME
from bracket.utils.id_types import (
    PlayerId,
    RankingId,
    StageId,
    StageItemId,
    StageItemInputId,
    TeamId,
    TournamentId,
)


@dataclass
class Scope:
    tournament: orm.Tournament
    stage: orm.Stage
    item: orm.StageItem
    ranking: orm.Ranking
    round: orm.Round
    match: orm.Match
    inputs: list[orm.StageItemInput]
    player: orm.Player
    team: orm.Team

    @property
    def tournament_id(self) -> TournamentId:
        return TournamentId(self.tournament.id)


async def create_scope(session: AsyncSession, name: str) -> Scope:
    club = orm.Club(name=name)
    session.add(club)
    await session.flush()
    tournament = orm.Tournament(
        name=name, club_id=club.id, start_time=DUMMY_MOCK_TIME, dashboard_public=False
    )
    session.add(tournament)
    await session.flush()
    stage = orm.Stage(name="Groups", tournament_id=tournament.id)
    ranking = orm.Ranking(
        tournament_id=tournament.id,
        position=0,
        win_points=Decimal(1),
        draw_points=Decimal("0.5"),
        loss_points=Decimal(0),
        add_score_points=False,
    )
    team = orm.Team(name="Team", tournament_id=tournament.id)
    player = orm.Player(
        name="Player",
        tournament_id=tournament.id,
        active=True,
        elo_score=1200,
        swiss_score=0,
        wins=0,
        draws=0,
        losses=0,
    )
    session.add_all([stage, ranking, team, player])
    await session.flush()
    item = orm.StageItem(
        name="Swiss",
        stage_id=stage.id,
        tournament_id=tournament.id,
        type=StageType.SWISS,
        team_count=2,
        ranking_id=ranking.id,
    )
    session.add(item)
    await session.flush()
    inputs = [
        orm.StageItemInput(
            tournament_id=tournament.id,
            stage_item_id=item.id,
            slot=index + 1,
            team_id=team.id if index == 0 else None,
        )
        for index in range(2)
    ]
    round_ = orm.Round(
        tournament_id=tournament.id, stage_item_id=item.id, name="Round 01", is_draft=True
    )
    session.add_all([round_, *inputs])
    await session.flush()
    match = orm.Match(
        tournament_id=tournament.id,
        round_id=round_.id,
        stage_item_input1_id=inputs[0].id,
        stage_item_input2_id=inputs[1].id,
        duration_minutes=10,
        margin_minutes=5,
        stage_item_input1_conflict=False,
        stage_item_input2_conflict=False,
        stage_item_input1_score=0,
        stage_item_input2_score=0,
    )
    session.add(match)
    await session.flush()
    return Scope(tournament, stage, item, ranking, round_, match, inputs, player, team)


@pytest_asyncio.fixture(loop_scope="session")
async def command_scopes() -> AsyncIterator[tuple[AsyncSession, Scope, Scope]]:
    async with session_factory() as session:
        local = await create_scope(session, "Local commands")
        foreign = await create_scope(session, "Foreign commands")
        try:
            yield session, local, foreign
        finally:
            await session.rollback()


@pytest.mark.asyncio(loop_scope="session")
async def test_stage_item_creation_scopes_stage_and_ranking(
    command_scopes: tuple[AsyncSession, Scope, Scope],
) -> None:
    session, local, foreign = command_scopes
    body = StageItemCreateBody(
        stage_id=StageId(local.stage.id),
        ranking_id=RankingId(local.ranking.id),
        type=StageType.SWISS,
        team_count=2,
    )
    await validate_stage_item_create(session, local.tournament_id, body)
    for field, foreign_id, kind in (
        ("stage_id", foreign.stage.id, "Stage"),
        ("ranking_id", foreign.ranking.id, "Ranking"),
    ):
        with pytest.raises(HTTPException) as error:
            await validate_stage_item_create(
                session, local.tournament_id, body.model_copy(update={field: foreign_id})
            )
        assert error.value.status_code == 400
        assert error.value.detail == f"Could not find {kind}(s) with ID {foreign_id}"


@pytest.mark.asyncio(loop_scope="session")
async def test_round_creation_scopes_its_stage_item(
    command_scopes: tuple[AsyncSession, Scope, Scope],
) -> None:
    session, local, foreign = command_scopes
    await validate_round_create(
        session, local.tournament_id, RoundCreateBody(stage_item_id=StageItemId(local.item.id))
    )
    with pytest.raises(HTTPException) as error:
        await validate_round_create(
            session,
            local.tournament_id,
            RoundCreateBody(stage_item_id=StageItemId(foreign.item.id)),
        )
    assert error.value.status_code == 400


@pytest.mark.asyncio(loop_scope="session")
async def test_match_creation_scopes_every_reference(
    command_scopes: tuple[AsyncSession, Scope, Scope],
) -> None:
    session, local, foreign = command_scopes
    data = {
        "round_id": local.round.id,
        "stage_item_input1_id": local.inputs[0].id,
        "stage_item_input2_id": local.inputs[1].id,
    }
    round_ = await validate_match_create(
        session, local.tournament_id, MatchCreateBodyFrontend.model_validate(data)
    )
    assert round_.id == local.round.id
    for field, foreign_id in (
        ("round_id", foreign.round.id),
        ("stage_item_input1_id", foreign.inputs[0].id),
        ("stage_item_input2_id", foreign.inputs[1].id),
        ("stage_item_input1_winner_from_match_id", foreign.match.id),
        ("stage_item_input2_winner_from_match_id", foreign.match.id),
    ):
        with pytest.raises(HTTPException) as error:
            await validate_match_create(
                session,
                local.tournament_id,
                MatchCreateBodyFrontend.model_validate(data | {field: foreign_id}),
            )
        assert error.value.status_code == 400


@pytest.mark.asyncio(loop_scope="session")
async def test_player_validation_is_scoped_and_skips_empty_sets(
    command_scopes: tuple[AsyncSession, Scope, Scope],
) -> None:
    session, local, foreign = command_scopes
    statements: list[str] = []

    def record(_conn: object, _cursor: object, statement: str, *_args: object) -> None:
        statements.append(statement)

    connection = (await session.connection()).sync_connection
    event.listen(connection, "before_cursor_execute", record)
    try:
        await validate_player_ids(session, local.tournament_id, set())
        assert statements == []
        await validate_player_ids(session, local.tournament_id, {PlayerId(local.player.id)})
        assert len(statements) == 1
        assert "matches" not in statements[0].lower()
        with pytest.raises(HTTPException) as error:
            await validate_player_ids(
                session,
                local.tournament_id,
                {PlayerId(local.player.id), PlayerId(foreign.player.id)},
            )
        assert error.value.status_code == 400
    finally:
        event.remove(connection, "before_cursor_execute", record)


@pytest.mark.asyncio(loop_scope="session")
async def test_slot_updates_scope_team_and_source(
    command_scopes: tuple[AsyncSession, Scope, Scope],
) -> None:
    session, local, foreign = command_scopes
    current = await get_stage_item_input_by_id(
        session, local.tournament_id, StageItemInputId(local.inputs[0].id)
    )
    target = StageItem.model_validate(local.item)
    for body in (
        StageItemInputUpdateBodyFinal(team_id=TeamId(foreign.team.id)),
        StageItemInputUpdateBodyTentative(
            winner_from_stage_item_id=StageItemId(foreign.item.id), winner_position=1
        ),
    ):
        with pytest.raises(HTTPException) as error:
            await validate_stage_item_input_update(
                session, local.tournament_id, current, body, target
            )
        assert error.value.status_code == 404


@pytest.mark.asyncio(loop_scope="session")
@pytest.mark.parametrize(
    ("format_", "team_count", "round_count", "match_count", "flush_budget"),
    [(StageType.ROUND_ROBIN, 64, 63, 2016, 4), (StageType.SINGLE_ELIMINATION, 32, 5, 31, 8)],
)
async def test_stage_generation_batches_writes_and_preserves_pairings(
    command_scopes: tuple[AsyncSession, Scope, Scope],
    format_: StageType,
    team_count: int,
    round_count: int,
    match_count: int,
    flush_budget: int,
) -> None:
    session, local, _ = command_scopes
    flushes = 0
    inserts = 0

    def flushed(*_: object) -> None:
        nonlocal flushes
        flushes += 1

    def executed(_conn: object, _cursor: object, statement: str, *_args: object) -> None:
        nonlocal inserts
        if statement.lstrip().lower().startswith("insert"):
            inserts += 1

    connection = (await session.connection()).sync_connection
    event.listen(session.sync_session, "after_flush", flushed)
    event.listen(connection, "before_cursor_execute", executed)
    try:
        item = await sql_create_stage_item_with_empty_inputs(
            session,
            local.tournament_id,
            StageItemCreateBody(
                stage_id=StageId(local.stage.id),
                ranking_id=RankingId(local.ranking.id),
                type=format_,
                team_count=team_count,
            ),
        )
        await build_matches_for_stage_item(session, item, local.tournament_id)
    finally:
        event.remove(session.sync_session, "after_flush", flushed)
        event.remove(connection, "before_cursor_execute", executed)
    assert flushes <= flush_budget
    assert inserts <= flush_budget + 3
    rounds = list(
        await session.scalars(
            select(orm.Round).where(orm.Round.stage_item_id == item.id).order_by(orm.Round.id)
        )
    )
    assert [round_.name for round_ in rounds] == [f"Round {n + 1:02d}" for n in range(round_count)]
    matches = list(
        await session.scalars(
            select(orm.Match).where(orm.Match.round_id.in_([r.id for r in rounds]))
        )
    )
    assert len(matches) == match_count
    assert all(match.tournament_id == local.tournament_id for match in matches)
    if format_ is StageType.ROUND_ROBIN:
        input_ids = list(
            await session.scalars(
                select(orm.StageItemInput.id).where(orm.StageItemInput.stage_item_id == item.id)
            )
        )
        pairs: set[tuple[int, int]] = set()
        for match in matches:
            assert match.stage_item_input1_id is not None
            assert match.stage_item_input2_id is not None
            first, second = sorted((match.stage_item_input1_id, match.stage_item_input2_id))
            pairs.add((first, second))
        assert pairs == set(combinations(sorted(input_ids), 2))
    else:
        by_id = {match.id: match for match in matches}
        for match in matches:
            for source_id in (
                match.stage_item_input1_winner_from_match_id,
                match.stage_item_input2_winner_from_match_id,
            ):
                if source_id is not None:
                    assert by_id[source_id].round_id < match.round_id
