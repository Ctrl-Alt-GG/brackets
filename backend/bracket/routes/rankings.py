from fastapi import APIRouter, Depends, HTTPException
from starlette import status

from bracket.config import config
from bracket.database import DbConnection
from bracket.logic.ranking.calculation import (
    get_team_rankings_lookup_for_tournament,
    recalculate_ranking_for_stage_item,
)
from bracket.logic.ranking.elimination import (
    update_inputs_in_complete_elimination_stage_item,
)
from bracket.logic.subscriptions import check_requirement
from bracket.models.db.ranking import Ranking, RankingBody, RankingCreateBody
from bracket.models.db.stage_item import StageType
from bracket.models.db.tournament import Tournament
from bracket.models.db.user import UserPublic
from bracket.routes.auth import (
    user_authenticated_for_tournament,
    user_authenticated_or_public_dashboard,
)
from bracket.routes.models import (
    RankingsResponse,
    StageItemInputStanding,
    StandingsResponse,
    SuccessResponse,
)
from bracket.routes.util import disallow_archived_tournament, ranking_dependency
from bracket.sql.rankings import (
    get_all_rankings_in_tournament,
    sql_create_ranking,
    sql_delete_ranking,
    sql_update_ranking,
)
from bracket.sql.stage_item_inputs import get_stage_item_ids_by_ranking_id
from bracket.sql.stage_items import get_stage_item
from bracket.sql.stages import get_full_tournament_details
from bracket.utils.id_types import RankingId, TournamentId

router = APIRouter(prefix=config.api_prefix)


@router.get("/tournaments/{tournament_id}/rankings")
async def get_rankings(
    conn: DbConnection,
    tournament_id: TournamentId,
    _: UserPublic = Depends(user_authenticated_or_public_dashboard),
) -> RankingsResponse:
    return RankingsResponse(data=await get_all_rankings_in_tournament(conn, tournament_id))


@router.get("/tournaments/{tournament_id}/standings")
async def get_standings(
    conn: DbConnection,
    tournament_id: TournamentId,
    _: UserPublic | None = Depends(user_authenticated_or_public_dashboard),
) -> StandingsResponse:
    """
    Get the teams of every stage item, best first. Teams advance to the next stage in this order.
    """
    stages = await get_full_tournament_details(conn, tournament_id, no_draft_rounds=True)
    team_rankings = await get_team_rankings_lookup_for_tournament(conn, tournament_id, stages)
    return StandingsResponse(
        data={
            stage_item_id: [
                StageItemInputStanding(stage_item_input_id=input_id, **statistics.model_dump())
                for input_id, statistics in team_ranking
            ]
            for stage_item_id, team_ranking in team_rankings.items()
        }
    )


@router.put("/tournaments/{tournament_id}/rankings/{ranking_id}")
async def update_ranking_by_id(
    conn: DbConnection,
    tournament_id: TournamentId,
    ranking_id: RankingId,
    ranking_body: RankingBody,
    _: UserPublic = Depends(user_authenticated_for_tournament),
    __: Tournament = Depends(disallow_archived_tournament),
    ___: Ranking = Depends(ranking_dependency),
) -> SuccessResponse:
    await sql_update_ranking(
        conn,
        tournament_id=tournament_id,
        ranking_id=ranking_id,
        ranking_body=ranking_body,
    )
    stage_item_ids = await get_stage_item_ids_by_ranking_id(conn, tournament_id, ranking_id)
    for stage_item_id in stage_item_ids:
        stage_item = await get_stage_item(conn, tournament_id, stage_item_id)
        await recalculate_ranking_for_stage_item(conn, tournament_id, stage_item)

        if stage_item.type == StageType.SINGLE_ELIMINATION:
            await update_inputs_in_complete_elimination_stage_item(conn, stage_item)
    return SuccessResponse()


@router.delete("/tournaments/{tournament_id}/rankings/{ranking_id}")
async def delete_ranking(
    conn: DbConnection,
    tournament_id: TournamentId,
    ranking_id: RankingId,
    _: UserPublic = Depends(user_authenticated_for_tournament),
    __: Tournament = Depends(disallow_archived_tournament),
    ___: Ranking = Depends(ranking_dependency),
) -> SuccessResponse:
    stage_item_ids = await get_stage_item_ids_by_ranking_id(conn, tournament_id, ranking_id)
    if stage_item_ids:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=(
                f"Could not delete ranking since it's used by {len(stage_item_ids)} stage items"
            ),
        )

    await sql_delete_ranking(conn, tournament_id, ranking_id)
    return SuccessResponse()


@router.post("/tournaments/{tournament_id}/rankings")
async def create_ranking(
    conn: DbConnection,
    ranking_body: RankingCreateBody,
    tournament_id: TournamentId,
    user: UserPublic = Depends(user_authenticated_for_tournament),
    _: Tournament = Depends(disallow_archived_tournament),
) -> SuccessResponse:
    existing_rankings = await get_all_rankings_in_tournament(conn, tournament_id)
    check_requirement(existing_rankings, user, "max_rankings")

    highest_position = (
        max(x.position for x in existing_rankings) if len(existing_rankings) > 0 else -1
    )
    await sql_create_ranking(conn, tournament_id, ranking_body, highest_position + 1)
    return SuccessResponse()
