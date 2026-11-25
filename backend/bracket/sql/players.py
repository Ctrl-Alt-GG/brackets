"""
Players as they are stored. They are shared by every tournament.

The players of one tournament, with the teams they play for there, are in
`bracket.sql.participation`.
"""

from collections import defaultdict
from collections.abc import Collection

from heliclockter import datetime_utc
from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from bracket import orm
from bracket.models.db.player import Player, PlayerBody
from bracket.utils.id_types import PlayerId


async def get_players(session: AsyncSession) -> list[Player]:
    """Every player, by name."""
    entities = await session.scalars(
        select(orm.Player)
        .order_by(orm.Player.name, orm.Player.id)
        .execution_options(populate_existing=True)
    )
    return [Player.model_validate(entity) for entity in entities]


async def get_player(session: AsyncSession, player_id: PlayerId) -> Player | None:
    entity = await session.get(orm.Player, player_id, populate_existing=True)
    return Player.model_validate(entity) if entity is not None else None


async def get_existing_player_ids(
    session: AsyncSession, player_ids: Collection[PlayerId]
) -> set[PlayerId]:
    """Those of these players that exist."""
    if not player_ids:
        return set()
    return {
        PlayerId(player_id)
        for player_id in await session.scalars(
            select(orm.Player.id).where(orm.Player.id.in_(player_ids))
        )
    }


async def get_players_by_name(
    session: AsyncSession, names: Collection[str]
) -> dict[str, list[Player]]:
    """The players with these names, regardless of case. Keyed by the name in lowercase."""
    if not names:
        return {}
    entities = await session.scalars(
        select(orm.Player)
        .where(func.lower(orm.Player.name).in_({name.lower() for name in names}))
        .order_by(orm.Player.id)
    )
    players: defaultdict[str, list[Player]] = defaultdict(list)
    for entity in entities:
        players[entity.name.lower()].append(Player.model_validate(entity))
    return dict(players)


async def insert_players(session: AsyncSession, names: list[str]) -> list[PlayerId]:
    entities = [orm.Player(name=name, created=datetime_utc.now()) for name in names]
    session.add_all(entities)
    await session.flush()
    return [PlayerId(entity.id) for entity in entities]


async def sql_update_player(
    session: AsyncSession, player_id: PlayerId, body: PlayerBody
) -> Player | None:
    entity = await session.get(orm.Player, player_id)
    if entity is None:
        return None
    entity.name = body.name
    await session.flush()
    return Player.model_validate(entity)


async def sql_delete_player(session: AsyncSession, player_id: PlayerId) -> None:
    """Delete the player, who leaves every team and every tournament's lineup."""
    await session.execute(delete(orm.Player).where(orm.Player.id == player_id))
