"""
Players as they are stored.

Their results are worked out from the matches instead: see `bracket.logic.ranking.players`, which
also owns sorting by results.
"""

from collections.abc import Mapping
from typing import Any

from heliclockter import datetime_utc
from sqlalchemy import delete, exists, func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import InstrumentedAttribute

from bracket import orm
from bracket.models.db.player import Player, PlayerBody
from bracket.models.results import START_ELO
from bracket.utils.id_types import PlayerId, TournamentId
from bracket.utils.pagination import ParticipantPagination

STORED_SORT_COLUMNS: Mapping[str, InstrumentedAttribute[Any]] = {
    "name": orm.Player.name,
    "active": orm.Player.active,
    "created": orm.Player.created,
}


async def get_all_players_in_tournament(
    session: AsyncSession,
    tournament_id: TournamentId,
    *,
    not_in_team: bool = False,
    pagination: ParticipantPagination | None = None,
) -> list[Player]:
    """The players by name. With `pagination` by a stored field, only that page in that order."""
    query = select(orm.Player).where(orm.Player.tournament_id == tournament_id)
    if not_in_team:
        query = query.where(~exists().where(orm.PlayerXTeam.player_id == orm.Player.id))
    if pagination is not None and pagination.sorts_by_results:
        raise ValueError("Results aren't stored: sorting by them happens in bracket.logic")
    if pagination is not None:
        sort_column = STORED_SORT_COLUMNS[pagination.sort_by]
        query = (
            query.order_by(
                sort_column.desc() if pagination.sort_direction == "desc" else sort_column.asc(),
                orm.Player.id,
            )
            .limit(pagination.limit)
            .offset(pagination.offset)
        )
    else:
        query = query.order_by(orm.Player.name, orm.Player.id)
    entities = await session.scalars(query.execution_options(populate_existing=True))
    return [Player.model_validate(entity) for entity in entities]


async def get_player_by_id(
    session: AsyncSession, player_id: PlayerId, tournament_id: TournamentId
) -> Player | None:
    entity = await session.scalar(
        select(orm.Player)
        .where(orm.Player.id == player_id, orm.Player.tournament_id == tournament_id)
        .execution_options(populate_existing=True)
    )
    return Player.model_validate(entity) if entity is not None else None


async def get_player_count(
    session: AsyncSession,
    tournament_id: TournamentId,
    *,
    not_in_team: bool = False,
) -> int:
    query = (
        select(func.count())
        .select_from(orm.Player)
        .where(orm.Player.tournament_id == tournament_id)
    )
    if not_in_team:
        query = query.where(~exists().where(orm.PlayerXTeam.player_id == orm.Player.id))
    return int(await session.scalar(query) or 0)


async def sql_update_player(
    session: AsyncSession, tournament_id: TournamentId, player_id: PlayerId, body: PlayerBody
) -> Player | None:
    entity = await session.scalar(
        select(orm.Player).where(
            orm.Player.id == player_id, orm.Player.tournament_id == tournament_id
        )
    )
    if entity is None:
        return None
    entity.name = body.name
    entity.active = body.active
    await session.flush()
    return Player.model_validate(entity)


async def sql_delete_player(
    session: AsyncSession, tournament_id: TournamentId, player_id: PlayerId
) -> None:
    await session.execute(
        delete(orm.Player).where(
            orm.Player.id == player_id, orm.Player.tournament_id == tournament_id
        )
    )


async def insert_players(
    session: AsyncSession, tournament_id: TournamentId, names: list[str], *, active: bool
) -> list[PlayerId]:
    entities = [
        orm.Player(
            name=name,
            active=active,
            created=datetime_utc.now(),
            tournament_id=tournament_id,
            elo_score=float(START_ELO),
            swiss_score=0.0,
            wins=0,
            draws=0,
            losses=0,
        )
        for name in names
    ]
    session.add_all(entities)
    await session.flush()
    return [PlayerId(entity.id) for entity in entities]


async def insert_player(
    session: AsyncSession, player_body: PlayerBody, tournament_id: TournamentId
) -> PlayerId:
    [player_id] = await insert_players(
        session, tournament_id, [player_body.name], active=player_body.active
    )
    return player_id
