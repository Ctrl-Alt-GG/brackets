from fastapi import APIRouter, Depends, HTTPException

from bracket.config import config
from bracket.database import DbSession
from bracket.logic.planning.conflicts import handle_conflicts
from bracket.logic.ranking.calculation import recalculate_ranking_for_stage_item
from bracket.models.db.match import is_played
from bracket.models.db.stage_item_inputs import (
    StageItemInputUpdateBody,
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
from bracket.sql.stage_item_inputs import get_stage_item_input_by_id, sql_update_stage_item_input
from bracket.sql.stage_items import get_stage_item
from bracket.sql.stages import get_full_tournament_details
from bracket.sql.validation import validate_stage_item_input_update
from bracket.utils.errors import (
    ForeignKey,
    UniqueIndex,
    check_foreign_key_violation,
    check_unique_constraint_violation,
)
from bracket.utils.id_types import StageItemId, StageItemInputId, TournamentId

router = APIRouter(prefix=config.api_prefix)


@router.put(
    "/tournaments/{tournament_id}/stage_items/{stage_item_id}/inputs/{stage_item_input_id}",
    response_model=SuccessResponse,
)
async def update_stage_item_input(
    session: DbSession,
    tournament_id: TournamentId,
    stage_item_id: StageItemId,
    stage_item_input_id: StageItemInputId,
    stage_item_body: StageItemInputUpdateBody,
    _: UserPublic = Depends(user_authenticated_for_tournament),
    stage_item: StageItemWithRounds = Depends(stage_item_dependency),
    ___: Tournament = Depends(disallow_archived_tournament),
) -> SuccessResponse:
    stage_item_input = await get_stage_item_input_by_id(session, tournament_id, stage_item_input_id)
    await validate_stage_item_input_update(
        session, tournament_id, stage_item_input, stage_item_body, stage_item
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

    with (
        check_unique_constraint_violation(
            {
                UniqueIndex.stage_item_inputs_stage_item_id_team_id_key,
                UniqueIndex.stage_item_inputs_stage_item_id_winner_from_stage_item_id_w_key,
            },
        ),
        check_foreign_key_violation({ForeignKey.stage_item_inputs_team_id_fkey}),
    ):
        await sql_update_stage_item_input(
            session, tournament_id, stage_item_id, stage_item_input_id, stage_item_body
        )
    await recalculate_ranking_for_stage_item(
        session, tournament_id, await get_stage_item(session, tournament_id, stage_item_id)
    )
    await handle_conflicts(session, await get_full_tournament_details(session, tournament_id))
    return SuccessResponse()
