import math
from collections import defaultdict
from decimal import Decimal

from sqlalchemy.ext.asyncio import AsyncConnection

from bracket.logic.ranking.statistics import START_ELO, TeamStatistics
from bracket.models.db.match import MatchWithDetailsDefinitive
from bracket.models.db.ranking import Ranking
from bracket.models.db.stage_item import StageType
from bracket.models.db.util import StageItemWithRounds, StageWithStageItems
from bracket.sql.rankings import get_ranking_for_stage_item
from bracket.sql.teams import update_team_stats
from bracket.utils.id_types import StageItemId, StageItemInputId, TournamentId
from bracket.utils.types import assert_some

K = 32
D = 400

StageItemXTeamRanking = dict[StageItemId, list[tuple[StageItemInputId, TeamStatistics]]]


def set_statistics_for_stage_item_input(
    team_index: int,
    stats: defaultdict[StageItemInputId, TeamStatistics],
    match: MatchWithDetailsDefinitive,
    stage_item_input_id: StageItemInputId,
    ranking: Ranking,
    stage_item: StageItemWithRounds,
    ratings_before: tuple[Decimal, Decimal],
) -> None:
    is_team1 = team_index == 0
    team_score = match.stage_item_input1_score if is_team1 else match.stage_item_input2_score
    opponent_score = match.stage_item_input2_score if is_team1 else match.stage_item_input1_score
    was_draw = match.stage_item_input1_score == match.stage_item_input2_score
    has_won = not was_draw and team_score == max(
        match.stage_item_input1_score, match.stage_item_input2_score
    )

    stats[stage_item_input_id].score_for += team_score
    stats[stage_item_input_id].score_against += opponent_score

    if has_won:
        stats[stage_item_input_id].wins += 1
        swiss_score_diff = ranking.win_points
    elif was_draw:
        stats[stage_item_input_id].draws += 1
        swiss_score_diff = ranking.draw_points
    else:
        stats[stage_item_input_id].losses += 1
        swiss_score_diff = ranking.loss_points

    if ranking.add_score_points:
        swiss_score_diff += team_score

    match stage_item.type:
        case StageType.ROUND_ROBIN | StageType.SINGLE_ELIMINATION:
            stats[stage_item_input_id].points += swiss_score_diff

        case StageType.SWISS:
            rating_diff = (ratings_before[1] - ratings_before[0]) * (1 if is_team1 else -1)
            expected_score = Decimal(1.0 / (1.0 + math.pow(10.0, rating_diff / D)))
            stats[stage_item_input_id].points += int(K * (swiss_score_diff - expected_score))

        case _:
            raise ValueError(f"Unsupported stage type: {stage_item.type}")


def determine_ranking_for_stage_item(
    stage_item: StageItemWithRounds,
    ranking: Ranking,
) -> defaultdict[StageItemInputId, TeamStatistics]:
    """
    Replay the played matches of a stage item in order and total the results of every input.

    A match counts once it has a score, because an unplayed match reads as 0-0. Every input with a
    team is included, also before it has played. In Swiss stage items the points are an ELO rating
    that starts at START_ELO, and every match changes it based on the ratings before that match.
    """
    initial_points = START_ELO if stage_item.type is StageType.SWISS else Decimal("0.00")
    input_x_stats: defaultdict[StageItemInputId, TeamStatistics] = defaultdict(
        lambda: TeamStatistics(points=initial_points)
    )
    for input_ in stage_item.inputs:
        if input_.team_id is not None:
            input_x_stats[input_.id] = TeamStatistics(points=initial_points)

    matches = [
        match
        for round_ in sorted(stage_item.rounds, key=lambda round_: round_.id)
        if not round_.is_draft
        for match in sorted(round_.matches, key=lambda match: match.id)
        if isinstance(match, MatchWithDetailsDefinitive)
        if match.stage_item_input1_score != 0 or match.stage_item_input2_score != 0
    ]
    for match in matches:
        ratings_before = (
            input_x_stats[match.stage_item_input1.id].points,
            input_x_stats[match.stage_item_input2.id].points,
        )
        for team_index, stage_item_input in enumerate(match.stage_item_inputs):
            set_statistics_for_stage_item_input(
                team_index,
                input_x_stats,
                match,
                stage_item_input.id,
                ranking,
                stage_item,
                ratings_before,
            )

    return input_x_stats


def determine_team_ranking_for_stage_item(
    stage_item: StageItemWithRounds,
    ranking: Ranking,
) -> list[tuple[StageItemInputId, TeamStatistics]]:
    """
    The inputs of a stage item, best first: the standings, and the order in which teams advance.

    Points decide. Ties are broken by score difference, then by the total score, then by the
    number of wins. Teams that are still level keep the order of their slots.
    """
    slots = {input_.id: input_.slot for input_ in stage_item.inputs}
    team_ranking = determine_ranking_for_stage_item(stage_item, ranking)
    return sorted(
        team_ranking.items(),
        key=lambda item: (
            -item[1].points,
            -item[1].score_difference,
            -item[1].score_for,
            -item[1].wins,
            slots[item[0]],
        ),
    )


async def get_team_rankings_lookup_for_tournament(
    conn: AsyncConnection, tournament_id: TournamentId, stages: list[StageWithStageItems]
) -> StageItemXTeamRanking:
    stage_items = {
        stage_item.id: stage_item for stage in stages for stage_item in stage.stage_items
    }
    return {
        stage_item_id: determine_team_ranking_for_stage_item(
            stage_item,
            assert_some(await get_ranking_for_stage_item(conn, tournament_id, stage_item.id)),
        )
        for stage_item_id, stage_item in stage_items.items()
    }


async def recalculate_ranking_for_stage_item(
    conn: AsyncConnection,
    tournament_id: TournamentId,
    stage_item: StageItemWithRounds,
) -> None:
    ranking = await get_ranking_for_stage_item(conn, tournament_id, stage_item.id)
    assert stage_item, "Stage item not found"
    assert ranking, "Ranking not found"

    team_x_stage_item_input_lookup = {
        stage_item_input.team_id: stage_item_input.id
        for stage_item_input in stage_item.inputs
        if stage_item_input.team_id is not None
    }

    elo_per_input = determine_ranking_for_stage_item(stage_item, ranking)

    for stage_item_input_id in team_x_stage_item_input_lookup.values():
        await update_team_stats(
            conn, tournament_id, stage_item_input_id, elo_per_input[stage_item_input_id]
        )
