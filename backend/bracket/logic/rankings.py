"""The points rules that rank the teams of stage items."""

from fastapi import HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from starlette import status

from bracket.logic.ranking.calculation import recalculate_ranking_for_stage_item
from bracket.logic.ranking.elimination import update_inputs_in_complete_elimination_stage_item
from bracket.logic.subscriptions import Limit, check_requirement
from bracket.logic.tournament_graph import TournamentGraph
from bracket.models.db.ranking import RankingBody, RankingCreateBody
from bracket.models.db.user import UserPublic
from bracket.models.enums import StageType
from bracket.sql.rankings import (
    get_all_rankings_in_tournament,
    sql_create_ranking,
    sql_delete_ranking,
    sql_update_ranking,
)
from bracket.sql.stage_items import get_stage_item_ids_by_ranking_id
from bracket.sql.stages import get_full_tournament_details
from bracket.utils.id_types import RankingId, TournamentId


async def create_ranking(
    session: AsyncSession, tournament_id: TournamentId, body: RankingCreateBody, user: UserPublic
) -> None:
    """Add a ranking after the tournament's others."""
    existing_rankings = await get_all_rankings_in_tournament(session, tournament_id)
    check_requirement(Limit.RANKINGS, len(existing_rankings), user)

    position = max((ranking.position for ranking in existing_rankings), default=-1) + 1
    await sql_create_ranking(session, tournament_id, body, position)


async def update_ranking(
    session: AsyncSession, tournament_id: TournamentId, ranking_id: RankingId, body: RankingBody
) -> None:
    """Change a ranking's rules or position, and rank the stage items that use it again."""
    await sql_update_ranking(session, tournament_id, ranking_id, body)

    stage_item_ids = await get_stage_item_ids_by_ranking_id(session, tournament_id, ranking_id)
    if not stage_item_ids:
        return
    graph = TournamentGraph(
        await get_full_tournament_details(
            session, tournament_id, stage_item_ids=set(stage_item_ids)
        )
    )
    for stage_item in graph.stage_items():
        await recalculate_ranking_for_stage_item(session, tournament_id, stage_item)
        if stage_item.type is StageType.SINGLE_ELIMINATION:
            await update_inputs_in_complete_elimination_stage_item(session, graph, stage_item)


async def delete_ranking(
    session: AsyncSession, tournament_id: TournamentId, ranking_id: RankingId
) -> None:
    stage_item_ids = await get_stage_item_ids_by_ranking_id(session, tournament_id, ranking_id)
    if stage_item_ids:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=(
                f"Could not delete ranking since it's used by {len(stage_item_ids)} stage items"
            ),
        )

    # New stage items take the first ranking unless they name one.
    if len(await get_all_rankings_in_tournament(session, tournament_id)) <= 1:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="A tournament needs at least one ranking",
        )

    await sql_delete_ranking(session, tournament_id, ranking_id)
