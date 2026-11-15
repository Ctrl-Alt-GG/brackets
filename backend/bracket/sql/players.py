from heliclockter import datetime_utc
from sqlalchemy import delete, exists, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from bracket import orm
from bracket.logic.ranking.statistics import START_ELO
from bracket.models.db.player import Player, PlayerBody
from bracket.utils.id_types import PlayerId, TournamentId
from bracket.utils.pagination import PaginationPlayers


async def get_all_players_in_tournament(
    session: AsyncSession,
    tournament_id: TournamentId,
    *,
    not_in_team: bool = False,
    pagination: PaginationPlayers | None = None,
) -> list[Player]:
    query = select(orm.Player).where(orm.Player.tournament_id == tournament_id)
    if not_in_team:
        query = query.where(~exists().where(orm.PlayerXTeam.player_id == orm.Player.id))
    sort_columns = {
        "name": orm.Player.name,
        "elo_score": orm.Player.elo_score,
        "swiss_score": orm.Player.swiss_score,
        "wins": orm.Player.wins,
        "draws": orm.Player.draws,
        "losses": orm.Player.losses,
        "active": orm.Player.active,
        "created": orm.Player.created,
    }
    sort_column = sort_columns[pagination.sort_by if pagination is not None else "name"]
    query = query.order_by(
        sort_column.desc()
        if pagination is not None and pagination.sort_direction == "desc"
        else sort_column.asc(),
        orm.Player.id,
    )
    if pagination is not None:
        query = query.limit(pagination.limit).offset(pagination.offset)
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


async def insert_player(
    session: AsyncSession, player_body: PlayerBody, tournament_id: TournamentId
) -> PlayerId:
    entity = orm.Player(
        name=player_body.name,
        active=player_body.active,
        created=datetime_utc.now(),
        tournament_id=tournament_id,
        elo_score=float(START_ELO),
        swiss_score=0.0,
        wins=0,
        draws=0,
        losses=0,
    )
    session.add(entity)
    await session.flush()
    return PlayerId(entity.id)
