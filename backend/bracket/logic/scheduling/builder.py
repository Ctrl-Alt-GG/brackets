from collections.abc import Awaitable, Callable, Sequence
from typing import NamedTuple, assert_never

from sqlalchemy.ext.asyncio import AsyncSession

from bracket.logic.ranking.calculation import recalculate_ranking_for_stage_item
from bracket.logic.scheduling.elimination import (
    build_single_elimination_stage_item,
    get_number_of_rounds_to_create_single_elimination,
)
from bracket.logic.scheduling.round_robin import (
    build_round_robin_stage_item,
    get_number_of_rounds_to_create_round_robin,
)
from bracket.models.db.participation import TournamentTeam
from bracket.models.db.stage_item import StageItem
from bracket.models.db.stage_item_inputs import (
    StageItemInputFinal,
    StageItemInputOptionFinal,
    StageItemInputOptionTentative,
    StageItemInputTentative,
)
from bracket.models.db.stage_tree import StageItemWithRounds, StageWithStageItems
from bracket.models.db.tournament import Tournament
from bracket.models.enums import StageType
from bracket.sql.rounds import sql_create_rounds
from bracket.sql.stage_items import get_stage_item
from bracket.sql.tournaments import sql_get_tournament
from bracket.utils.id_types import StageId, StageItemId, TournamentId

MatchBuilder = Callable[[AsyncSession, Tournament, StageItemWithRounds], Awaitable[None]]


class StageFormat(NamedTuple):
    """The rounds a new stage item gets, and what fills them with matches."""

    rounds: int
    # `None` for Swiss, whose rounds are drawn one at a time later.
    build_matches: MatchBuilder | None


def get_stage_format(stage_type: StageType, team_count: int) -> StageFormat:
    match stage_type:
        case StageType.ROUND_ROBIN:
            return StageFormat(
                get_number_of_rounds_to_create_round_robin(team_count),
                build_round_robin_stage_item,
            )
        case StageType.SINGLE_ELIMINATION:
            return StageFormat(
                get_number_of_rounds_to_create_single_elimination(team_count),
                build_single_elimination_stage_item,
            )
        case StageType.SWISS:
            return StageFormat(0, None)
        case _:
            assert_never(stage_type)


async def build_matches_for_stage_item(
    session: AsyncSession, stage_item: StageItem, tournament_id: TournamentId
) -> None:
    """Give a new stage item the rounds and matches of its format."""
    stage_format = get_stage_format(stage_item.type, stage_item.team_count)
    if stage_format.build_matches is None:
        return

    await sql_create_rounds(
        session,
        tournament_id,
        stage_item.id,
        [f"Round {index + 1:02d}" for index in range(stage_format.rounds)],
        is_draft=False,
    )
    stage_item_with_rounds = await get_stage_item(session, tournament_id, stage_item.id)
    tournament = await sql_get_tournament(session, tournament_id)
    await stage_format.build_matches(session, tournament, stage_item_with_rounds)
    await recalculate_ranking_for_stage_item(session, tournament_id, stage_item_with_rounds)


def determine_available_inputs(
    teams: Sequence[TournamentTeam],
    stages: list[StageWithStageItems],
) -> dict[StageId, list[StageItemInputOptionTentative | StageItemInputOptionFinal]]:
    """
    What the slots of each stage can take: a team that takes part in the tournament, or a place
    of a group or Swiss stage item of an earlier stage.
    """
    all_team_options = {
        team.id: StageItemInputOptionFinal(team_id=team.id, already_taken=False) for team in teams
    }
    # Add inputs from non-elimination stage items that can be used in the next stage.
    # Elimination stage items have no "outputs" but are final.
    all_tentative_options = {
        (stage_item.id, winner_position): StageItemInputOptionTentative(
            winner_from_stage_item_id=stage_item.id,
            winner_position=winner_position,
            already_taken=False,
        )
        for stage in stages
        for stage_item in stage.stage_items
        if stage_item.type in {StageType.ROUND_ROBIN, StageType.SWISS}
        for winner_position in range(1, stage_item.team_count + 1)
    }

    # Determine which inputs have been used (set `already_taken` to True)
    for stage in stages:
        for stage_item in stage.stage_items:
            for input_ in stage_item.inputs:
                match input_:
                    case StageItemInputFinal() as final if input_.team_id in all_team_options:
                        all_team_options[final.team_id].already_taken = True

                    case StageItemInputTentative() as tentative:
                        if (key := tentative.get_lookup_key()) in all_tentative_options:
                            all_tentative_options[key].already_taken = True

    # Loop through stage items once more to assemble the final results and make sure
    # tentative inputs are only available after the stage item that they originate from.
    # We start with all teams but not tentative inputs.
    results_teams = all_team_options.copy()
    results_tentative: dict[tuple[StageItemId, int], StageItemInputOptionTentative] = {}
    results = {}

    for stage in stages:
        results[stage.id] = list(results_teams.values()) + list(results_tentative.values())

        # Add options for subsequent stage items for the tentative "outputs" from this round
        for stage_item in stage.stage_items:
            for (option_stage_item_id, option_win_pos), option in all_tentative_options.items():
                if option_stage_item_id == stage_item.id:
                    results_tentative[(option_stage_item_id, option_win_pos)] = option

    return results
