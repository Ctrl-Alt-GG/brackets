from collections import defaultdict

from fastapi import HTTPException
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncConnection
from starlette import status

from bracket.logic.ranking.calculation import (
    StageItemXTeamRanking,
    get_team_rankings_lookup_for_tournament,
    recalculate_ranking_for_stage_item,
)
from bracket.logic.ranking.elimination import update_inputs_in_complete_elimination_stage_item
from bracket.models.db.match import is_played
from bracket.models.db.stage_item import StageType
from bracket.models.db.stage_item_inputs import (
    StageItemInputFinal,
    StageItemInputTentative,
)
from bracket.models.db.team import Team
from bracket.models.db.util import StageItemWithRounds, StageWithStageItems
from bracket.sql.matches import clear_results_for_matches_in_stage_item
from bracket.sql.stage_item_inputs import (
    get_stage_item_input_by_id,
    sql_set_team_id_for_stage_item_input,
)
from bracket.sql.stage_items import get_stage_item
from bracket.sql.stages import get_full_tournament_details
from bracket.utils.id_types import (
    StageId,
    StageItemId,
    StageItemInputId,
    TournamentId,
)


class StageItemInputUpdate(BaseModel):
    stage_item_input: StageItemInputTentative
    team: Team


def determine_team_id(
    winner_from_stage_item_id: StageItemId,
    winner_position: int,
    stage_item_x_team_rankings: StageItemXTeamRanking,
) -> StageItemInputId | None:
    """
    The input that holds this position in the ranking of an earlier stage item.

    `None` while that ranking is shorter than the position: a group with an open slot ranks
    fewer teams than it has slots.
    """
    team_ranking = stage_item_x_team_rankings.get(winner_from_stage_item_id, [])
    if len(team_ranking) < winner_position:
        return None

    return team_ranking[winner_position - 1][0]


async def get_team_update_for_input(
    conn: AsyncConnection,
    tournament_id: TournamentId,
    stage_item_input: StageItemInputTentative,
    stage_item_x_team_rankings: StageItemXTeamRanking,
) -> StageItemInputUpdate | None:
    """The team that takes this slot when its stage starts, or `None` while that is undecided."""
    target_stage_item_input_id = determine_team_id(
        stage_item_input.winner_from_stage_item_id,
        stage_item_input.winner_position,
        stage_item_x_team_rankings,
    )
    if target_stage_item_input_id is None:
        return None

    target_stage_item_input = await get_stage_item_input_by_id(
        conn, tournament_id, target_stage_item_input_id
    )
    if not isinstance(target_stage_item_input, StageItemInputFinal):
        return None

    return StageItemInputUpdate(
        stage_item_input=stage_item_input, team=target_stage_item_input.team
    )


def describe_unresolved_input(
    stage_item: StageItemWithRounds,
    stage_item_input: StageItemInputTentative,
    stages: list[StageWithStageItems],
) -> str:
    source = next(
        (
            candidate
            for stage in stages
            for candidate in stage.stage_items
            if candidate.id == stage_item_input.winner_from_stage_item_id
        ),
        None,
    )
    source_name = source.name if source is not None else "an earlier stage item"
    return (
        f"Slot {stage_item_input.slot} of {stage_item.name} takes "
        f"#{stage_item_input.winner_position} of {source_name}, which doesn't have that many teams"
    )


async def get_updates_to_inputs_in_activated_stage(
    conn: AsyncConnection,
    tournament_id: TournamentId,
    stage_id: StageId,
    *,
    strict: bool = False,
) -> dict[StageItemId, list[StageItemInputUpdate]]:
    """
    Gets the team_id updates for stage item inputs of the newly activated stage.

    A slot that takes a position its source can't fill yet is left out, so that the organizer
    can still open the tournament and fix it. With `strict`, as when the stage is activated, it
    is an error instead.
    """
    stages = await get_full_tournament_details(conn, tournament_id)
    team_rankings_per_stage_item = await get_team_rankings_lookup_for_tournament(
        conn, tournament_id, stages
    )
    activated_stage = next((stage for stage in stages if stage.id == stage_id), None)
    assert activated_stage

    result = defaultdict(list)
    unresolved: list[str] = []

    for stage_item in activated_stage.stage_items:
        for stage_item_input in stage_item.inputs:
            if not isinstance(stage_item_input, StageItemInputTentative):
                continue

            update = await get_team_update_for_input(
                conn, tournament_id, stage_item_input, team_rankings_per_stage_item
            )
            if update is not None:
                result[stage_item.id].append(update)
            else:
                unresolved.append(describe_unresolved_input(stage_item, stage_item_input, stages))

    if strict and unresolved:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=(
                f"{unresolved[0]}. Assign the missing teams in the current stage, or change "
                "the slot."
            ),
        )

    return dict(result)


async def update_matches_in_activated_stage(
    conn: AsyncConnection, tournament_id: TournamentId, stage_id: StageId
) -> None:
    """
    Sets the team_id for stage item inputs of the newly activated stage.
    """
    updates_per_stage_item = await get_updates_to_inputs_in_activated_stage(
        conn, tournament_id, stage_id, strict=True
    )
    for stage_item_updates in updates_per_stage_item.values():
        for update in stage_item_updates:
            await sql_set_team_id_for_stage_item_input(
                conn, tournament_id, update.stage_item_input.id, update.team.id
            )


def count_results_in_stage(stage: StageWithStageItems) -> int:
    """How many matches of the stage have a result, which going back a stage discards."""
    return sum(
        is_played(match)
        for stage_item in stage.stage_items
        for round_ in stage_item.rounds
        for match in round_.matches
    )


async def update_matches_in_deactivated_stage(
    conn: AsyncConnection, tournament_id: TournamentId, deactivated_stage: StageWithStageItems
) -> None:
    """
    Releases the teams that advanced into the deactivated stage, and discards its results.

    The results belong to the teams that had advanced. Going forward again can put other teams in
    those slots, so the results can't be kept.
    """
    for stage_item in deactivated_stage.stage_items:
        await clear_results_for_matches_in_stage_item(conn, tournament_id, stage_item.id)

        for stage_item_input in stage_item.inputs:
            if stage_item_input.winner_from_stage_item_id is not None:
                await sql_set_team_id_for_stage_item_input(
                    conn, tournament_id, stage_item_input.id, None
                )

        # Without results there are no winners, so the later rounds of a bracket empty out, and
        # the statistics kept with every slot start over.
        cleared_stage_item = await get_stage_item(conn, tournament_id, stage_item.id)
        if cleared_stage_item.type is StageType.SINGLE_ELIMINATION:
            await update_inputs_in_complete_elimination_stage_item(conn, cleared_stage_item)

        await recalculate_ranking_for_stage_item(
            conn, tournament_id, await get_stage_item(conn, tournament_id, stage_item.id)
        )
