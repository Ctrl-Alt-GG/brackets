"""
Players, which every organizer shares. The players of one tournament are in
`bracket.routes.participation`.
"""

from fastapi import APIRouter

from bracket.config import config
from bracket.database import DbSession
from bracket.logic.players import update_player
from bracket.models.db.player import PlayerBody, PlayerMultiBody
from bracket.routes.access import AuthenticatedUser
from bracket.routes.models import PlayersResponse, SinglePlayerResponse, SuccessResponse
from bracket.sql.players import get_player, get_players, insert_players, sql_delete_player
from bracket.utils.id_types import PlayerId
from bracket.utils.types import assert_some

router = APIRouter(prefix=config.api_prefix)


@router.get("/players", response_model=PlayersResponse)
async def get_all_players(session: DbSession, _: AuthenticatedUser) -> PlayersResponse:
    """Every player by name. The teams they are in come with the teams."""
    return PlayersResponse(data=await get_players(session))


@router.post("/players", response_model=SinglePlayerResponse)
async def create_player(
    session: DbSession, body: PlayerBody, _: AuthenticatedUser
) -> SinglePlayerResponse:
    [player_id] = await insert_players(session, [body.name])
    return SinglePlayerResponse(data=assert_some(await get_player(session, player_id)))


@router.post("/players_multi", response_model=SuccessResponse)
async def create_players(
    session: DbSession, body: PlayerMultiBody, _: AuthenticatedUser
) -> SuccessResponse:
    await insert_players(session, body.player_names)
    return SuccessResponse()


@router.put("/players/{player_id}", response_model=SinglePlayerResponse)
async def rename_player(
    session: DbSession, player_id: PlayerId, body: PlayerBody, _: AuthenticatedUser
) -> SinglePlayerResponse:
    return SinglePlayerResponse(data=await update_player(session, player_id, body))


@router.delete("/players/{player_id}", response_model=SuccessResponse)
async def delete_player(
    session: DbSession, player_id: PlayerId, _: AuthenticatedUser
) -> SuccessResponse:
    """Delete the player, who leaves their teams and the lineups of every tournament."""
    await sql_delete_player(session, player_id)
    return SuccessResponse()
