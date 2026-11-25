"""Which teams take the slots of a stage when it is activated."""

from collections import defaultdict
from typing import Literal

from fastapi import HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from starlette import status

from bracket.logic.ranking.calculation import get_team_rankings_lookup_for_tournament
from bracket.models.db.match import is_played
from bracket.models.db.participation import TournamentTeam
from bracket.models.db.stage_item_inputs import (
    StageItemInputFinal,
    StageItemInputTentative,
    StageItemInputUpdate,
)
from bracket.models.db.stage_tree import StageItemWithRounds, StageWithStageItems
from bracket.utils.i18n import gettext
from bracket.utils.id_types import StageId, StageItemId, StageItemInputId, TeamId, TournamentId


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
    return source.label if source is not None else gettext("an earlier stage item")


async def get_updates_to_inputs_in_activated_stage(
    session: AsyncSession,
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
    team_rankings = await get_team_rankings_lookup_for_tournament(session, tournament_id, stages)
    activated_stage = next(stage for stage in stages if stage.id == stage_id)
    teams_by_input: dict[StageItemInputId, TournamentTeam] = {
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
                    gettext(
                        "Slot {slot} of {stage_item} takes #{position} of {source}, which doesn't "
                        "have that many teams",
                        position=position,
                        slot=stage_item_input.slot,
                        source=source_name(stage_item_input, stages),
                        stage_item=stage_item.label,
                    )
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
            detail=gettext(
                "{problem}. Assign the missing teams in the current stage, or change the slot.",
                problem=unresolved[0],
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
                gettext(
                    "slot {slot} ({source} #{position})",
                    position=update.stage_item_input.winner_position,
                    slot=input_.slot,
                    source=source_name(update.stage_item_input, stages),
                )
            )
        elif isinstance(input_, StageItemInputFinal):
            names[input_.team_id] = input_.team.name
            slots_per_team[input_.team_id].append(gettext("slot {slot}", slot=input_.slot))

    for team_id, slots in slots_per_team.items():
        if len(slots) > 1:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=gettext(
                    "{team} would take {slots} of {stage_item}, but a team can have only one "
                    "slot in it. Change one of those slots, then activate the stage.",
                    slots=gettext(" and ").join(slots),
                    stage_item=stage_item.label,
                    team=names[team_id],
                ),
            )


def count_results_in_stage(stage: StageWithStageItems) -> int:
    """How many matches of the stage have a result, which going back a stage discards."""
    return sum(
        is_played(match)
        for stage_item in stage.stage_items
        for round_ in stage_item.rounds
        for match in round_.matches
    )
