from decimal import Decimal

from heliclockter import datetime_utc
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncConnection

from bracket.logic.ranking.statistics import START_ELO
from bracket.models.db.player import Player, PlayerBody, PlayerToInsert
from bracket.schema import players
from bracket.utils.id_types import PlayerId, TournamentId
from bracket.utils.pagination import PaginationPlayers
from bracket.utils.types import dict_without_none


async def get_all_players_in_tournament(
    conn: AsyncConnection,
    tournament_id: TournamentId,
    *,
    not_in_team: bool = False,
    pagination: PaginationPlayers | None = None,
) -> list[Player]:
    not_in_team_filter = "AND players.team_id IS NULL" if not_in_team else ""
    limit_filter = "LIMIT :limit" if pagination is not None and pagination.limit is not None else ""
    offset_filter = (
        "OFFSET :offset" if pagination is not None and pagination.offset is not None else ""
    )
    sort_by = pagination.sort_by if pagination is not None else "name"
    sort_direction = pagination.sort_direction if pagination is not None else ""
    query = f"""
        SELECT *
        FROM players
        WHERE players.tournament_id = :tournament_id
        {not_in_team_filter}
        ORDER BY {sort_by} {sort_direction}
        {limit_filter}
        {offset_filter}
        """

    result = await conn.execute(
        text(query),
        dict_without_none(
            {
                "tournament_id": tournament_id,
                "offset": pagination.offset if pagination is not None else None,
                "limit": pagination.limit if pagination is not None else None,
            }
        ),
    )

    return [Player.model_validate(x._mapping) for x in result]


async def get_player_by_id(
    conn: AsyncConnection, player_id: PlayerId, tournament_id: TournamentId
) -> Player | None:
    query = """
        SELECT *
        FROM players
        WHERE id = :player_id
        AND tournament_id = :tournament_id
    """
    result = (
        await conn.execute(text(query), {"player_id": player_id, "tournament_id": tournament_id})
    ).first()
    return Player.model_validate(result._mapping) if result is not None else None


async def get_player_count(
    conn: AsyncConnection,
    tournament_id: TournamentId,
    *,
    not_in_team: bool = False,
) -> int:
    not_in_team_filter = "AND players.team_id IS NULL" if not_in_team else ""
    query = f"""
        SELECT count(*)
        FROM players
        WHERE players.tournament_id = :tournament_id
        {not_in_team_filter}
        """
    return int(await conn.scalar(text(query), {"tournament_id": tournament_id}) or 0)


async def sql_delete_player(
    conn: AsyncConnection, tournament_id: TournamentId, player_id: PlayerId
) -> None:
    query = "DELETE FROM players WHERE id = :player_id AND tournament_id = :tournament_id"
    await conn.execute(text(query), {"player_id": player_id, "tournament_id": tournament_id})


async def sql_delete_players_of_tournament(
    conn: AsyncConnection, tournament_id: TournamentId
) -> None:
    query = "DELETE FROM players WHERE tournament_id = :tournament_id"
    await conn.execute(text(query), {"tournament_id": tournament_id})


async def insert_player(
    conn: AsyncConnection, player_body: PlayerBody, tournament_id: TournamentId
) -> None:
    await conn.execute(
        players.insert(),
        PlayerToInsert(
            **player_body.model_dump(),
            created=datetime_utc.now(),
            tournament_id=tournament_id,
            elo_score=START_ELO,
            swiss_score=Decimal("0.0"),
        ).model_dump(),
    )
