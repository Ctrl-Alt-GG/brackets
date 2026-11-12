import math
from collections import defaultdict
from decimal import Decimal

from sqlalchemy.ext.asyncio import AsyncConnection

from bracket.logic.ranking.statistics import START_ELO, D, K, PlayerStatistics
from bracket.models.db.match import MatchWithDetailsDefinitive, is_played
from bracket.models.db.player import Player
from bracket.models.db.stage_item_inputs import StageItemInputFinal
from bracket.models.db.team import FullTeamWithPlayers
from bracket.models.db.util import StageWithStageItems
from bracket.sql.players import get_all_players_in_tournament
from bracket.sql.stages import get_full_tournament_details
from bracket.sql.teams import get_teams_with_members
from bracket.utils.id_types import PlayerId, TournamentId
from bracket.utils.pagination import PaginationPlayers


def determine_player_statistics(
    stages: list[StageWithStageItems], teams: list[FullTeamWithPlayers]
) -> dict[PlayerId, PlayerStatistics]:
    """
    Replay every played match of the tournament in schedule order and total each player's results.

    Players get the results of the teams they are in. Their ELO rating starts at START_ELO, and
    every match moves it by how far the result differs from the expected one, which follows from
    the average ratings of both teams before the match. A match counts once it has a score,
    because an unplayed match reads as 0-0.
    """
    player_ids_per_team = {team.id: team.player_ids for team in teams}
    ratings: defaultdict[PlayerId, float] = defaultdict(lambda: float(START_ELO))
    statistics: defaultdict[PlayerId, PlayerStatistics] = defaultdict(PlayerStatistics)

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
            rating_diff = team_ratings[1 - index] - team_ratings[index]
            expected_result = 1.0 / (1.0 + math.pow(10.0, rating_diff / D))
            result = (
                Decimal(1)
                if score > opponent_score
                else Decimal("0.5")
                if score == opponent_score
                else Decimal(0)
            )

            for player_id in player_ids:
                ratings[player_id] += K * (float(result) - expected_result)
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
    conn: AsyncConnection,
    tournament_id: TournamentId,
    *,
    stages: list[StageWithStageItems] | None = None,
    teams: list[FullTeamWithPlayers] | None = None,
) -> dict[PlayerId, PlayerStatistics]:
    """`stages` (without draft rounds) and `teams` can be passed by a caller that has them."""
    if stages is None:
        stages = await get_full_tournament_details(conn, tournament_id, no_draft_rounds=True)
    if teams is None:
        teams = await get_teams_with_members(conn, tournament_id)
    return determine_player_statistics(stages, teams)


async def get_players_with_statistics(
    conn: AsyncConnection,
    tournament_id: TournamentId,
    *,
    not_in_team: bool = False,
    pagination: PaginationPlayers | None = None,
    stages: list[StageWithStageItems] | None = None,
    teams: list[FullTeamWithPlayers] | None = None,
) -> list[Player]:
    """
    The players with their results. Those follow from the match results, so they are worked out
    on every request instead of being read from the players table.
    """
    statistics = await get_player_statistics(conn, tournament_id, stages=stages, teams=teams)
    players = await get_all_players_in_tournament(
        conn, tournament_id, not_in_team=not_in_team, pagination=pagination
    )
    return [
        player.model_copy(update=statistics.get(player.id, PlayerStatistics()).model_dump())
        for player in players
    ]
