from collections import defaultdict
from typing import Literal

from fastapi import HTTPException
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession
from starlette import status

from bracket.logic.ranking.calculation import (
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
from bracket.sql.stage_item_inputs import sql_set_team_id_for_stage_item_input
from bracket.sql.stage_items import get_stage_item
from bracket.utils.errors import UniqueIndex, check_unique_constraint_violation
from bracket.utils.id_types import StageId, StageItemId, StageItemInputId, TeamId, TournamentId


class StageItemInputUpdate(BaseModel):
    stage_item_input: StageItemInputTentative
    team: Team
    # A team that is level with `team` on every criterion, but goes elsewhere or doesn't go
    # through: only their seeding decided which of the two takes this slot.
    tied_team: Team | None = None


def get_adjacent_stage(
    stages: list[StageWithStageItems], direction: Literal["next", "previous"]
) -> StageWithStageItems | None:
    """
    The stage that activating the next or previous stage activates. Before any stage is active,
    the next stage is the first one, and there is no previous one.
    """
    ordered = sorted(stages, key=lambda stage: stage.id)
    active = next((index for index, stage in enumerate(ordered) if stage.is_active), None)
    if active is None:
        return ordered[0] if direction == "next" and ordered else None

    index = active + 1 if direction == "next" else active - 1
    return ordered[index] if 0 <= index < len(ordered) else None


def source_name(
    stage_item_input: StageItemInputTentative, stages: list[StageWithStageItems]
) -> str:
    """The name of the earlier stage item that a slot takes a team from."""
    source = next(
        (
            candidate
            for stage in stages
            for candidate in stage.stage_items
            if candidate.id == stage_item_input.winner_from_stage_item_id
        ),
        None,
    )
    return (source.name or source.type_name) if source is not None else "an earlier stage item"


async def get_updates_to_inputs_in_activated_stage(
    conn: AsyncSession,
    tournament_id: TournamentId,
    stages: list[StageWithStageItems],
    stage_id: StageId,
    *,
    strict: bool = False,
) -> dict[StageItemId, list[StageItemInputUpdate]]:
    """
    The teams that take the slots of a stage when it is activated, by the standings of the stage
    items those slots take places of.

    A slot that takes a place its source can't fill yet is left out, so that the organizer can
    still open the tournament and fix it. With `strict`, as when the stage is activated, it is an
    error instead.
    """
    team_rankings = await get_team_rankings_lookup_for_tournament(conn, tournament_id, stages)
    activated_stage = next(stage for stage in stages if stage.id == stage_id)
    teams_by_input: dict[StageItemInputId, Team] = {
        input_.id: input_.team
        for stage in stages
        for stage_item in stage.stage_items
        for input_ in stage_item.inputs
        if isinstance(input_, StageItemInputFinal)
    }
    # The stage item that each place of an earlier stage item moves on to.
    targets = {
        (input_.winner_from_stage_item_id, input_.winner_position): stage_item
        for stage_item in activated_stage.stage_items
        for input_ in stage_item.inputs
        if isinstance(input_, StageItemInputTentative)
    }

    result: defaultdict[StageItemId, list[StageItemInputUpdate]] = defaultdict(list)
    unresolved: list[str] = []

    for stage_item in activated_stage.stage_items:
        for stage_item_input in stage_item.inputs:
            if not isinstance(stage_item_input, StageItemInputTentative):
                continue

            placings = team_rankings.get(stage_item_input.winner_from_stage_item_id, [])
            position = stage_item_input.winner_position
            team = (
                teams_by_input.get(placings[position - 1].stage_item_input_id)
                if position <= len(placings)
                else None
            )
            if team is None:
                unresolved.append(
                    f"Slot {stage_item_input.slot} of {stage_item.name} takes #{position} of "
                    f"{source_name(stage_item_input, stages)}, which doesn't have that many teams"
                )
                continue

            # Teams that both move on to this stage item meet there anyway. Otherwise seeding
            # decided which of two teams that are level on every criterion gets this place.
            tied_team = None
            next_target = targets.get((stage_item_input.winner_from_stage_item_id, position + 1))
            if (
                position < len(placings)
                and placings[position].tiebreak == placings[position - 1].tiebreak
                and (next_target is None or next_target.id != stage_item.id)
            ):
                tied_team = teams_by_input.get(placings[position].stage_item_input_id)

            result[stage_item.id].append(
                StageItemInputUpdate(
                    stage_item_input=stage_item_input, team=team, tied_team=tied_team
                )
            )

    if strict and unresolved:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=(
                f"{unresolved[0]}. Assign the missing teams in the current stage, or change "
                "the slot."
            ),
        )

    return dict(result)


def check_teams_take_one_slot_each(
    stage_item: StageItemWithRounds,
    updates: list[StageItemInputUpdate],
    stages: list[StageWithStageItems],
) -> None:
    """
    A team can have one slot in a stage item. It would get two when it qualifies from two groups,
    or qualifies for a slot while an organizer also put it in another one.
    """
    planned = {update.stage_item_input.id: update for update in updates}
    slots_per_team: defaultdict[TeamId, list[str]] = defaultdict(list)
    names: dict[TeamId, str] = {}
    for input_ in stage_item.inputs:
        if (update := planned.get(input_.id)) is not None:
            names[update.team.id] = update.team.name
            slots_per_team[update.team.id].append(
                f"slot {input_.slot} ({source_name(update.stage_item_input, stages)} "
                f"#{update.stage_item_input.winner_position})"
            )
        elif isinstance(input_, StageItemInputFinal):
            names[input_.team_id] = input_.team.name
            slots_per_team[input_.team_id].append(f"slot {input_.slot}")

    for team_id, slots in slots_per_team.items():
        if len(slots) > 1:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=(
                    f"{names[team_id]} would take {' and '.join(slots)} of "
                    f"{stage_item.name or stage_item.type_name}, but a team can have only one "
                    "slot in it. Change one of those slots, then activate the stage."
                ),
            )


async def update_matches_in_activated_stage(
    conn: AsyncSession,
    tournament_id: TournamentId,
    stages: list[StageWithStageItems],
    stage_id: StageId,
) -> None:
    """
    Puts the teams that move on into the slots of the newly activated stage.
    """
    updates_per_stage_item = await get_updates_to_inputs_in_activated_stage(
        conn, tournament_id, stages, stage_id, strict=True
    )
    activated_stage = next(stage for stage in stages if stage.id == stage_id)
    for stage_item in activated_stage.stage_items:
        check_teams_take_one_slot_each(
            stage_item, updates_per_stage_item.get(stage_item.id, []), stages
        )

    with check_unique_constraint_violation(
        {UniqueIndex.stage_item_inputs_stage_item_id_team_id_key}
    ):
        for stage_item_updates in updates_per_stage_item.values():
            for update in stage_item_updates:
                await sql_set_team_id_for_stage_item_input(
                    conn, tournament_id, update.stage_item_input.id, update.team.id
                )

    resolved_inputs = {
        update.stage_item_input.id: StageItemInputFinal.model_validate(
            update.stage_item_input.model_dump() | {"team_id": update.team.id, "team": update.team}
        )
        for updates in updates_per_stage_item.values()
        for update in updates
    }
    # Slots also appear inside matches. Replace every copy so the same loaded tree can be used
    # for conflict checks after activation, without a second eager graph load.
    for stage in stages:
        for stage_item in stage.stage_items:
            stage_item.inputs = [
                resolved_inputs.get(input_.id, input_) for input_ in stage_item.inputs
            ]
            for round_ in stage_item.rounds:
                for match in round_.matches:
                    if match.stage_item_input1_id in resolved_inputs:
                        match.stage_item_input1 = resolved_inputs[match.stage_item_input1_id]
                    if match.stage_item_input2_id in resolved_inputs:
                        match.stage_item_input2 = resolved_inputs[match.stage_item_input2_id]


def count_results_in_stage(stage: StageWithStageItems) -> int:
    """How many matches of the stage have a result, which going back a stage discards."""
    return sum(
        is_played(match)
        for stage_item in stage.stage_items
        for round_ in stage_item.rounds
        for match in round_.matches
    )


async def update_matches_in_deactivated_stage(
    conn: AsyncSession, tournament_id: TournamentId, deactivated_stage: StageWithStageItems
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
