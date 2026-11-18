from collections import defaultdict
from decimal import Decimal
from typing import NamedTuple

from sqlalchemy.ext.asyncio import AsyncSession

from bracket.logic.ranking.elo import K, expected_result
from bracket.models.db.match import MatchWithDetailsDefinitive, is_played
from bracket.models.db.ranking import Ranking
from bracket.models.db.stage_tree import StageItemWithRounds, StageWithStageItems
from bracket.models.enums import StageType
from bracket.models.results import START_ELO, TeamStatistics
from bracket.sql.rankings import get_all_rankings_in_tournament, get_ranking
from bracket.sql.stage_item_inputs import update_stage_item_input_statistics
from bracket.utils.id_types import StageItemId, StageItemInputId, TournamentId
from bracket.utils.types import assert_some


class Placing(NamedTuple):
    """A place in the standings of a stage item."""

    stage_item_input_id: StageItemInputId
    statistics: TeamStatistics
    # What ranks the team, compared in order and lowest first. Teams with the same values are
    # level on every criterion, and their seeding (the order of their slots) separates them.
    tiebreak: tuple[Decimal, ...]


StageItemXTeamRanking = dict[StageItemId, list[Placing]]


def result_points(ranking: Ranking, team_score: int, opponent_score: int) -> Decimal:
    """What a match earns a team by the rules of the ranking."""
    if team_score > opponent_score:
        points = ranking.win_points
    elif team_score == opponent_score:
        points = ranking.draw_points
    else:
        points = ranking.loss_points

    return points + team_score if ranking.add_score_points else points


def get_played_matches(stage_item: StageItemWithRounds) -> list[MatchWithDetailsDefinitive]:
    """
    The matches of the published rounds that have a result, in the order they were played. A match
    counts once it has a score, because an unplayed match reads as 0-0.
    """
    return [
        match
        for round_ in sorted(stage_item.rounds, key=lambda round_: round_.id)
        if not round_.is_draft
        for match in sorted(round_.matches, key=lambda match: match.id)
        if isinstance(match, MatchWithDetailsDefinitive)
        if is_played(match)
    ]


def determine_ranking_for_stage_item(
    stage_item: StageItemWithRounds,
    ranking: Ranking,
) -> defaultdict[StageItemInputId, TeamStatistics]:
    """
    Replay the played matches of a stage item in order and total the results of every input.

    Every input with a team is included, also before it has played. In Swiss stage items the
    points are an ELO rating that starts at START_ELO, and every match changes it based on the
    ratings before that match. Elsewhere they are what the ranking awards.
    """
    is_swiss = stage_item.type is StageType.SWISS
    initial_points = START_ELO if is_swiss else Decimal("0.00")
    input_x_stats: defaultdict[StageItemInputId, TeamStatistics] = defaultdict(
        lambda: TeamStatistics(points=initial_points)
    )
    for input_ in stage_item.inputs:
        if input_.team_id is not None:
            input_x_stats[input_.id] = TeamStatistics(points=initial_points)

    for match in get_played_matches(stage_item):
        scores = (match.stage_item_input1_score, match.stage_item_input2_score)
        # Both ratings move by the ratings before the match, so neither may see the other's update.
        ratings_before = [input_x_stats[input_id].points for input_id in match.stage_item_input_ids]
        for index, input_id in enumerate(match.stage_item_input_ids):
            team_score, opponent_score = scores[index], scores[1 - index]
            statistics = input_x_stats[input_id]
            statistics.score_for += team_score
            statistics.score_against += opponent_score

            if team_score > opponent_score:
                statistics.wins += 1
                result = Decimal(1)
            elif team_score == opponent_score:
                statistics.draws += 1
                result = Decimal("0.5")
            else:
                statistics.losses += 1
                result = Decimal(0)

            if is_swiss:
                # A rating moves by how far the result is from the expected one, on a scale of 0
                # to 1. What the ranking awards for a win doesn't belong on that scale: 3 points
                # for a win would raise the ratings of both teams of every match.
                expected = expected_result(
                    float(ratings_before[index]), float(ratings_before[1 - index])
                )
                statistics.points += int(K * (result - Decimal(expected)))
            else:
                statistics.points += result_points(ranking, team_score, opponent_score)

    return input_x_stats


class HeadToHead(NamedTuple):
    points: Decimal = Decimal(0)
    score_difference: int = 0


def determine_head_to_head(
    stage_item: StageItemWithRounds,
    ranking: Ranking,
    statistics: dict[StageItemInputId, TeamStatistics],
) -> dict[StageItemInputId, HeadToHead]:
    """
    For every team that has as many points as others: the points and the score difference it got
    in the matches between those teams only, by the rules of the ranking.
    """
    teams_per_points: defaultdict[Decimal, set[StageItemInputId]] = defaultdict(set)
    for input_id, input_statistics in statistics.items():
        teams_per_points[input_statistics.points].add(input_id)
    level_teams = {
        input_id: frozenset(teams)
        for teams in teams_per_points.values()
        if len(teams) > 1
        for input_id in teams
    }

    head_to_head: defaultdict[StageItemInputId, HeadToHead] = defaultdict(HeadToHead)
    for match in get_played_matches(stage_item):
        input1, input2 = match.stage_item_input_ids
        if input1 not in level_teams or level_teams[input1] != level_teams.get(input2):
            continue

        scores = (match.stage_item_input1_score, match.stage_item_input2_score)
        for index, input_id in enumerate((input1, input2)):
            team_score, opponent_score = scores[index], scores[1 - index]
            before = head_to_head[input_id]
            head_to_head[input_id] = HeadToHead(
                points=before.points + result_points(ranking, team_score, opponent_score),
                score_difference=before.score_difference + team_score - opponent_score,
            )

    return dict(head_to_head)


def determine_team_ranking_for_stage_item(
    stage_item: StageItemWithRounds,
    ranking: Ranking,
) -> list[Placing]:
    """
    The inputs of a stage item, best first: the standings, and the order in which teams advance.

    Points decide. Teams with the same points are compared by their matches against each other:
    first by the points those earned them, then by the score difference in them. After that, the
    score difference over all matches decides, then the total score, then the number of wins.
    Teams that are still level keep the order of their slots.
    """
    slots = {input_.id: input_.slot for input_ in stage_item.inputs}
    statistics = determine_ranking_for_stage_item(stage_item, ranking)
    head_to_head = determine_head_to_head(stage_item, ranking, statistics)
    placings = [
        Placing(
            stage_item_input_id=input_id,
            statistics=input_statistics,
            tiebreak=(
                -input_statistics.points,
                -head_to_head.get(input_id, HeadToHead()).points,
                Decimal(-head_to_head.get(input_id, HeadToHead()).score_difference),
                Decimal(-input_statistics.score_difference),
                Decimal(-input_statistics.score_for),
                Decimal(-input_statistics.wins),
            ),
        )
        for input_id, input_statistics in statistics.items()
    ]
    return sorted(
        placings, key=lambda placing: (placing.tiebreak, slots[placing.stage_item_input_id])
    )


async def get_team_rankings_lookup_for_tournament(
    session: AsyncSession, tournament_id: TournamentId, stages: list[StageWithStageItems]
) -> StageItemXTeamRanking:
    rankings = {
        ranking.id: ranking
        for ranking in await get_all_rankings_in_tournament(session, tournament_id)
    }
    return {
        stage_item.id: determine_team_ranking_for_stage_item(
            stage_item, rankings[stage_item.ranking_id]
        )
        for stage in stages
        for stage_item in stage.stage_items
    }


async def recalculate_ranking_for_stage_item(
    session: AsyncSession,
    tournament_id: TournamentId,
    stage_item: StageItemWithRounds,
) -> None:
    """Store the results of every slot of the stage item, which Swiss pairing reads."""
    ranking = assert_some(await get_ranking(session, tournament_id, stage_item.ranking_id))
    statistics = determine_ranking_for_stage_item(stage_item, ranking)

    # Empty slots need their initial statistics too. Rolling back a stage releases advanced
    # teams before recalculating; skipping their slots would retain the old teams' ratings
    # when another team advances into them later.
    await update_stage_item_input_statistics(
        session,
        tournament_id,
        {
            stage_item_input.id: statistics[stage_item_input.id]
            for stage_item_input in stage_item.inputs
        },
    )
