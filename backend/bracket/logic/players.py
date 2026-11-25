"""Players. They are shared by every tournament, where each plays for one of its teams."""

from fastapi import HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from starlette import status

from bracket.models.db.player import Player, PlayerBody
from bracket.sql.players import sql_update_player
from bracket.utils.i18n import gettext
from bracket.utils.id_types import PlayerId


async def update_player(session: AsyncSession, player_id: PlayerId, body: PlayerBody) -> Player:
    player = await sql_update_player(session, player_id, body)
    if player is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=gettext("Could not find player with id {id}", id=player_id),
        )
    return player
