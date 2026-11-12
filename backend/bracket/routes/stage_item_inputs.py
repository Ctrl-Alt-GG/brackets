from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncConnection
from starlette import status

from bracket.config import config
from bracket.database import DbConnection
from bracket.logic.planning.conflicts import handle_conflicts
from bracket.logic.ranking.calculation import recalculate_ranking_for_stage_item
from bracket.models.db.match import is_played
from bracket.models.db.stage_item import StageType
from bracket.models.db.stage_item_inputs import (
    StageItemInput,
    StageItemInputUpdateBody,
    StageItemInputUpdateBodyFinal,
    StageItemInputUpdateBodyTentative,
)
from bracket.models.db.tournament import Tournament
from bracket.models.db.user import UserPublic
from bracket.models.db.util import StageItemWithRounds
from bracket.routes.auth import (
    user_authenticated_for_tournament,
)
from bracket.routes.models import SuccessResponse
from bracket.routes.util import disallow_archived_tournament, stage_item_dependency
from bracket.sql.stage_item_inputs import get_stage_item_input_by_id
from bracket.sql.stage_items import get_stage_item
from bracket.sql.stages import get_full_tournament_details
from bracket.sql.teams import get_team_by_id
from bracket.utils.errors import (
    ForeignKey,
    UniqueIndex,
    check_foreign_key_violation,
    check_unique_constraint_violation,
)
from bracket.utils.id_types import StageItemId, StageItemInputId, TournamentId

router = APIRouter(prefix=config.api_prefix)


async def validate_stage_item_update(
    conn: AsyncConnection,
    stage_item_input_db: StageItemInput | None,
    stage_item_input_body: StageItemInputUpdateBody,
    tournament_id: TournamentId,
    stage_item: StageItemWithRounds,
) -> None:
    if stage_item_input_db is None or stage_item_input_db.stage_item_id != stage_item.id:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Could not find the stage item input",
        )

    if isinstance(stage_item_input_body, StageItemInputUpdateBodyTentative):
        input_id = stage_item_input_body.winner_from_stage_item_id
        # Empty unless the stage item is part of this tournament.
        source_stages = await get_full_tournament_details(
            conn, tournament_id, stage_item_ids={input_id}
        )
        if not source_stages or not source_stages[0].stage_items:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Could not find stage item with id {input_id}",
            )
        source = source_stages[0].stage_items[0]
        if source.stage_id >= stage_item.stage_id or source.type is StageType.SINGLE_ELIMINATION:
            raise HTTPException(400, "Choose a group or Swiss stage item from an earlier stage")
        if stage_item_input_body.winner_position > source.team_count:
            raise HTTPException(400, "The source stage item doesn't have that many team slots")

    if (
        isinstance(stage_item_input_body, StageItemInputUpdateBodyFinal)
        and await get_team_by_id(conn, stage_item_input_body.team_id, tournament_id) is None
    ):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Could not find team with id {stage_item_input_body.team_id}",
        )


@router.put(
    "/tournaments/{tournament_id}/stage_items/{stage_item_id}/inputs/{stage_item_input_id}",
    response_model=SuccessResponse,
)
async def update_stage_item_input(
    conn: DbConnection,
    tournament_id: TournamentId,
    stage_item_id: StageItemId,
    stage_item_input_id: StageItemInputId,
    stage_item_body: StageItemInputUpdateBody,
    _: UserPublic = Depends(user_authenticated_for_tournament),
    stage_item: StageItemWithRounds = Depends(stage_item_dependency),
    ___: Tournament = Depends(disallow_archived_tournament),
) -> SuccessResponse:
    stage_item_input = await get_stage_item_input_by_id(conn, tournament_id, stage_item_input_id)
    await validate_stage_item_update(
        conn, stage_item_input, stage_item_body, tournament_id, stage_item
    )
    assert stage_item_input is not None
    if isinstance(stage_item_body, StageItemInputUpdateBodyTentative):
        unchanged = (
            stage_item_input.winner_from_stage_item_id == stage_item_body.winner_from_stage_item_id
            and stage_item_input.winner_position == stage_item_body.winner_position
        )
    else:
        unchanged = (
            stage_item_input.team_id == stage_item_body.team_id
            and stage_item_input.winner_from_stage_item_id is None
        )
    if unchanged:
        return SuccessResponse()
    if any(
        is_played(match)
        and stage_item_input_id in (match.stage_item_input1_id, match.stage_item_input2_id)
        for round_ in stage_item.rounds
        for match in round_.matches
    ):
        raise HTTPException(
            400,
            "Clear this team's match results in Rounds before changing its slot. "
            "Recorded results must stay with the teams that played them.",
        )

    query = """
        UPDATE stage_item_inputs
        SET team_id = :team_id,
            winner_position = :winner_position,
            winner_from_stage_item_id = :winner_from_stage_item_id
        WHERE stage_item_inputs.id = :stage_item_input_id
        AND stage_item_inputs.tournament_id = :tournament_id
        AND stage_item_inputs.stage_item_id = :stage_item_id
    """
    with (
        check_unique_constraint_violation(
            {
                UniqueIndex.stage_item_inputs_stage_item_id_team_id_key,
                UniqueIndex.stage_item_inputs_stage_item_id_winner_from_stage_item_id_w_key,
            },
        ),
        check_foreign_key_violation({ForeignKey.stage_item_inputs_team_id_fkey}),
    ):
        await conn.execute(
            text(query),
            {
                "tournament_id": tournament_id,
                "stage_item_input_id": stage_item_input_id,
                "stage_item_id": stage_item_id,
                "team_id": stage_item_body.team_id
                if isinstance(stage_item_body, StageItemInputUpdateBodyFinal)
                else None,
                "winner_position": stage_item_body.winner_position
                if isinstance(stage_item_body, StageItemInputUpdateBodyTentative)
                else None,
                "winner_from_stage_item_id": stage_item_body.winner_from_stage_item_id
                if isinstance(stage_item_body, StageItemInputUpdateBodyTentative)
                else None,
            },
        )
    await recalculate_ranking_for_stage_item(
        conn, tournament_id, await get_stage_item(conn, tournament_id, stage_item_id)
    )
    await handle_conflicts(conn, await get_full_tournament_details(conn, tournament_id))
    return SuccessResponse()
