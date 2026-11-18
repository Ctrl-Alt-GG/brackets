from fastapi import HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from starlette import status

from bracket.logic.ranking.players import get_player_statistics, with_statistics
from bracket.logic.subscriptions import Limit, check_requirement
from bracket.models.db.player import Player, PlayerBody
from bracket.models.db.user import UserPublic
from bracket.sql.players import get_player_count, insert_players, sql_update_player
from bracket.utils.id_types import PlayerId, TournamentId


async def create_players(
    session: AsyncSession,
    tournament_id: TournamentId,
    names: list[str],
    *,
    active: bool,
    user: UserPublic,
) -> None:
    check_requirement(
        Limit.PLAYERS, await get_player_count(session, tournament_id), user, additions=len(names)
    )
    await insert_players(session, tournament_id, names, active=active)


async def update_player(
    session: AsyncSession, tournament_id: TournamentId, player_id: PlayerId, body: PlayerBody
) -> Player:
    player = await sql_update_player(session, tournament_id, player_id, body)
    if player is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Could not find player with id {player_id}",
        )
    return with_statistics(player, await get_player_statistics(session, tournament_id))
