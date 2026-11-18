"""Stages, and moving a tournament from one stage to another."""

from typing import Literal

from fastapi import HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from starlette import status

from bracket import orm
from bracket.logic.planning.conflicts import handle_conflicts
from bracket.logic.planning.matches import schedule_all_matches
from bracket.logic.ranking.calculation import recalculate_ranking_for_stage_item
from bracket.logic.ranking.elimination import update_inputs_in_complete_elimination_stage_item
from bracket.logic.ranking.team_totals import add_team_totals
from bracket.logic.scheduling.advancement import (
    check_teams_take_one_slot_each,
    count_results_in_stage,
    get_adjacent_stage,
    get_updates_to_inputs_in_activated_stage,
)
from bracket.logic.scheduling.builder import determine_available_inputs
from bracket.logic.subscriptions import Limit, check_requirement
from bracket.logic.tournament_graph import TournamentGraph
from bracket.models.db.stage import Stage, StageUpdateBody
from bracket.models.db.stage_item_inputs import (
    StageItemInputFinal,
    StageItemInputOptionFinal,
    StageItemInputOptionTentative,
    StageItemInputTentative,
    StageItemInputUpdate,
)
from bracket.models.db.stage_tree import StageWithStageItems
from bracket.models.db.user import UserPublic
from bracket.models.enums import StageType
from bracket.sql.matches import clear_results_for_matches_in_stage_item
from bracket.sql.stage_item_inputs import sql_set_team_id_for_stage_item_input
from bracket.sql.stages import (
    get_full_tournament_details,
    sql_activate_next_stage,
    sql_create_stage,
    sql_delete_stage,
    sql_update_stage,
)
from bracket.sql.teams import get_teams_with_members
from bracket.sql.tournaments import count_tournament_records
from bracket.utils.errors import UniqueIndex, check_unique_constraint_violation
from bracket.utils.id_types import StageId, StageItemId, TournamentId


async def get_stages_with_team_totals(
    session: AsyncSession, tournament_id: TournamentId, *, no_draft_rounds: bool
) -> list[StageWithStageItems]:
    graph = TournamentGraph(
        await get_full_tournament_details(session, tournament_id, no_draft_rounds=no_draft_rounds)
    )
    await add_team_totals(session, tournament_id, graph)
    return graph.stages


async def get_available_inputs(
    session: AsyncSession, tournament_id: TournamentId
) -> dict[StageId, list[StageItemInputOptionTentative | StageItemInputOptionFinal]]:
    stages = await get_full_tournament_details(session, tournament_id)
    teams = await get_teams_with_members(session, tournament_id)
    return determine_available_inputs(teams, stages)


async def get_advancement_preview(
    session: AsyncSession, tournament_id: TournamentId
) -> dict[StageItemId, list[StageItemInputUpdate]]:
    """The teams that would take the slots of the next stage if it were activated now."""
    graph = TournamentGraph(await get_full_tournament_details(session, tournament_id))
    await add_team_totals(session, tournament_id, graph)
    next_stage = get_adjacent_stage(graph.stages, "next")
    if next_stage is None:
        return {}
    return await get_updates_to_inputs_in_activated_stage(
        session, tournament_id, graph.stages, next_stage.id
    )


async def create_stage(
    session: AsyncSession, tournament_id: TournamentId, user: UserPublic
) -> None:
    check_requirement(
        Limit.STAGES, await count_tournament_records(session, orm.Stage, tournament_id), user
    )
    await sql_create_stage(session, tournament_id)


async def update_stage(
    session: AsyncSession, tournament_id: TournamentId, stage: Stage, body: StageUpdateBody
) -> None:
    await sql_update_stage(session, tournament_id, stage.id, body)
    if body.custom_duration_minutes != stage.custom_duration_minutes:
        await schedule_all_matches(session, tournament_id)


async def delete_stage(
    session: AsyncSession, tournament_id: TournamentId, stage: StageWithStageItems
) -> None:
    if len(stage.stage_items) > 0:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Stage contains stage items, please delete those first",
        )
    await sql_delete_stage(session, tournament_id, stage.id)


async def advance_teams_into_stage(
    session: AsyncSession, tournament_id: TournamentId, graph: TournamentGraph, stage_id: StageId
) -> None:
    """Put the teams that move on into the slots of the stage that is activated."""
    updates_per_stage_item = await get_updates_to_inputs_in_activated_stage(
        session, tournament_id, graph.stages, stage_id, strict=True
    )
    activated_stage = next(stage for stage in graph.stages if stage.id == stage_id)
    for stage_item in activated_stage.stage_items:
        check_teams_take_one_slot_each(
            stage_item, updates_per_stage_item.get(stage_item.id, []), graph.stages
        )

    updates = [update for updates in updates_per_stage_item.values() for update in updates]
    with check_unique_constraint_violation(
        {UniqueIndex.stage_item_inputs_stage_item_id_team_id_key}
    ):
        for update in updates:
            await sql_set_team_id_for_stage_item_input(
                session, tournament_id, update.stage_item_input.id, update.team.id
            )

    graph.replace_slots(
        {
            update.stage_item_input.id: StageItemInputFinal.model_validate(
                update.stage_item_input.model_dump()
                | {"team_id": update.team.id, "team": update.team}
            )
            for update in updates
        }
    )


async def release_teams_from_stage(
    session: AsyncSession,
    tournament_id: TournamentId,
    graph: TournamentGraph,
    stage: StageWithStageItems,
) -> None:
    """
    Release the teams that advanced into a stage that is deactivated, and discard its results.

    The results belong to the teams that had advanced. Going forward again can put other teams in
    those slots, so the results can't be kept.
    """
    for stage_item in stage.stage_items:
        await clear_results_for_matches_in_stage_item(session, tournament_id, stage_item.id)
        for round_ in stage_item.rounds:
            for match in round_.matches:
                graph.update_match(
                    match.id,
                    stage_item_input1_score=0,
                    stage_item_input2_score=0,
                    scoreless_result=False,
                )

        released = {
            slot.id: StageItemInputTentative.model_validate(slot.model_dump() | {"team_id": None})
            for slot in stage_item.inputs
            if isinstance(slot, StageItemInputFinal) and slot.winner_from_stage_item_id is not None
        }
        for slot_id in released:
            await sql_set_team_id_for_stage_item_input(session, tournament_id, slot_id, None)
        graph.replace_slots(released)

        # Without results there are no winners, so the later rounds of a bracket empty out, and
        # the statistics kept with every slot start over.
        if stage_item.type is StageType.SINGLE_ELIMINATION:
            await update_inputs_in_complete_elimination_stage_item(session, graph, stage_item)
        await recalculate_ranking_for_stage_item(session, tournament_id, stage_item)


async def activate_adjacent_stage(
    session: AsyncSession,
    tournament_id: TournamentId,
    direction: Literal["next", "previous"],
    *,
    discard_results: bool,
) -> None:
    """
    Activate the next stage, which fills its slots with the teams that advance, or go back to the
    previous one, which releases them again.
    """
    graph = TournamentGraph(await get_full_tournament_details(session, tournament_id))
    active_stage = next((stage for stage in graph.stages if stage.is_active), None)
    if direction == "previous" and active_stage is None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="No stage is active yet, so there is no previous stage to go back to",
        )

    new_active_stage = get_adjacent_stage(graph.stages, direction)
    if new_active_stage is None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"There is no {direction} stage",
        )

    if direction == "next":
        await advance_teams_into_stage(session, tournament_id, graph, new_active_stage.id)
    elif active_stage is not None:
        results = count_results_in_stage(active_stage)
        if results > 0 and not discard_results:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=(
                    f"Going back discards the {results} "
                    f"{'result' if results == 1 else 'results'} of {active_stage.name}. "
                    "Confirm that they can be discarded."
                ),
            )
        await release_teams_from_stage(session, tournament_id, graph, active_stage)

    await sql_activate_next_stage(session, new_active_stage.id, tournament_id)
    await handle_conflicts(session, graph)
