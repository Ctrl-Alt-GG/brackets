import math
from collections import defaultdict
from decimal import Decimal
from operator import attrgetter

from sqlalchemy.ext.asyncio import AsyncSession
from starlette.concurrency import run_in_threadpool

from bracket.logic.ranking.elo import K, expected_result
from bracket.models.db.match import MatchWithDetailsDefinitive, is_played
from bracket.models.db.participation import TournamentPlayer, TournamentTeamWithPlayers
from bracket.models.db.stage_item_inputs import StageItemInputFinal
from bracket.models.db.stage_tree import StageWithStageItems
from bracket.models.results import START_ELO, ResultTotals
from bracket.sql.participation import get_tournament_players, get_tournament_teams
from bracket.sql.stages import get_full_tournament_details
from bracket.utils.id_types import PlayerId, TournamentId
from bracket.utils.pagination import PlayerPagination


def determine_player_statistics(
    stages: list[StageWithStageItems], teams: list[TournamentTeamWithPlayers]
) -> dict[PlayerId, ResultTotals]:
    """
    Replay every played match of the tournament in schedule order and total each player's results.

    Players get the results of the team they play for in the tournament's lineup. Their ELO rating
    starts at START_ELO, and
    every match moves it by how far the result differs from the expected one, which follows from
    the average ratings of both teams before the match. A match counts once it has a score,
    because an unplayed match reads as 0-0.
    """
    player_ids_per_team = {team.id: team.player_ids for team in teams}
    ratings: defaultdict[PlayerId, float] = defaultdict(lambda: float(START_ELO))
    statistics: defaultdict[PlayerId, ResultTotals] = defaultdict(ResultTotals)

    matches = sorted(
        (
            match
            for stage in stages
            for stage_item in stage.stage_items
            for round_ in stage_item.rounds
            if not round_.is_draft
            for match in round_.matches
            if isinstance(match, MatchWithDetailsDefinitive)
            if is_played(match)
        ),
        key=lambda match: (
            match.start_time.timestamp() if match.start_time is not None else math.inf,
            match.round_id,
            match.id,
        ),
    )

    for match in matches:
        team_player_ids = [
            player_ids_per_team.get(input_.team_id, [])
            if isinstance(input_, StageItemInputFinal)
            else []
            for input_ in match.stage_item_inputs
        ]
        team_ratings = [
            sum(ratings[player_id] for player_id in player_ids) / len(player_ids)
            if len(player_ids) > 0
            else float(START_ELO)
            for player_ids in team_player_ids
        ]
        scores = (match.stage_item_input1_score, match.stage_item_input2_score)

        for index, player_ids in enumerate(team_player_ids):
            score, opponent_score = scores[index], scores[1 - index]
            expected = expected_result(team_ratings[index], team_ratings[1 - index])
            result = (
                Decimal(1)
                if score > opponent_score
                else Decimal("0.5")
                if score == opponent_score
                else Decimal(0)
            )

            for player_id in player_ids:
                ratings[player_id] += K * (float(result) - expected)
                player_statistics = statistics[player_id]
                player_statistics.swiss_score += result
                if score > opponent_score:
                    player_statistics.wins += 1
                elif score == opponent_score:
                    player_statistics.draws += 1
                else:
                    player_statistics.losses += 1

    for player_id, player_statistics in statistics.items():
        player_statistics.elo_score = Decimal(round(ratings[player_id]))

    return dict(statistics)


async def get_player_statistics(
    session: AsyncSession,
    tournament_id: TournamentId,
    *,
    stages: list[StageWithStageItems] | None = None,
    teams: list[TournamentTeamWithPlayers] | None = None,
) -> dict[PlayerId, ResultTotals]:
    """`stages` (without draft rounds) and `teams` can be passed by a caller that has them."""
    if stages is None:
        stages = await get_full_tournament_details(session, tournament_id, no_draft_rounds=True)
    if teams is None:
        teams = await get_tournament_teams(session, tournament_id)
    # Replaying every match is the longest step of a tournament's pages. In a worker thread, other
    # requests are still answered while it runs.
    return await run_in_threadpool(determine_player_statistics, stages, teams)


def with_statistics(
    player: TournamentPlayer, statistics: dict[PlayerId, ResultTotals]
) -> TournamentPlayer:
    return player.model_copy(update=statistics.get(player.id, ResultTotals()).model_dump())


async def get_players_with_statistics(
    session: AsyncSession,
    tournament_id: TournamentId,
    *,
    pagination: PlayerPagination | None = None,
    stages: list[StageWithStageItems] | None = None,
    teams: list[TournamentTeamWithPlayers] | None = None,
) -> list[TournamentPlayer]:
    """
    The tournament's players with their results there. Those follow from the match results, so
    they are worked out on every request, and sorting by them happens here, before the page is
    cut.
    """
    statistics = await get_player_statistics(session, tournament_id, stages=stages, teams=teams)
    if pagination is None or not pagination.sorts_by_results:
        players = await get_tournament_players(session, tournament_id, pagination=pagination)
        return [with_statistics(player, statistics) for player in players]

    players = [
        with_statistics(player, statistics)
        for player in await get_tournament_players(session, tournament_id)
    ]
    players.sort(key=attrgetter("id"))
    players.sort(key=attrgetter(pagination.sort_by), reverse=pagination.sort_direction == "desc")
    return players[pagination.offset : pagination.offset + pagination.limit]
