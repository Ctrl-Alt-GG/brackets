import math
from collections import defaultdict
from decimal import Decimal

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncConnection

from bracket.logic.ranking.statistics import START_ELO, D, K, TeamTotals
from bracket.utils.id_types import TeamId, TournamentId


async def get_team_totals(
    conn: AsyncConnection, tournament_id: TournamentId
) -> dict[TeamId, TeamTotals]:
    """Replay published results in schedule order, including corrections and deletions.

    Read the small match projection directly so team totals can also enrich embedded teams in
    stage responses without recursing through the full stage loader.
    """
    rows = await conn.execute(
        text(
            """
            SELECT i1.team_id AS team1, i2.team_id AS team2,
                   m.stage_item_input1_score AS score1, m.stage_item_input2_score AS score2
            FROM matches m
            JOIN rounds r ON r.id = m.round_id
            JOIN stage_items si ON si.id = r.stage_item_id
            JOIN stages s ON s.id = si.stage_id
            JOIN stage_item_inputs i1 ON i1.id = m.stage_item_input1_id AND i1.stage_item_id = si.id
            JOIN stage_item_inputs i2 ON i2.id = m.stage_item_input2_id AND i2.stage_item_id = si.id
            WHERE s.tournament_id = :tournament_id AND r.is_draft IS FALSE
              AND i1.team_id IS NOT NULL AND i2.team_id IS NOT NULL
              AND i1.team_id <> i2.team_id
              AND (m.stage_item_input1_score <> 0 OR m.stage_item_input2_score <> 0
                   OR m.scoreless_result)
            ORDER BY m.start_time NULLS LAST, r.id, m.id
            """
        ),
        {"tournament_id": tournament_id},
    )
    totals: defaultdict[TeamId, TeamTotals] = defaultdict(TeamTotals)
    ratings: defaultdict[TeamId, float] = defaultdict(lambda: float(START_ELO))
    for row in rows:
        team_ids = (TeamId(row.team1), TeamId(row.team2))
        scores = (row.score1, row.score2)
        before = (ratings[team_ids[0]], ratings[team_ids[1]])
        for index, team_id in enumerate(team_ids):
            score, opponent_score = scores[index], scores[1 - index]
            result = 1.0 if score > opponent_score else 0.5 if score == opponent_score else 0.0
            expected = 1.0 / (1.0 + math.pow(10.0, (before[1 - index] - before[index]) / D))
            ratings[team_id] += K * (result - expected)
            total = totals[team_id]
            total.swiss_score += Decimal(str(result))
            if score > opponent_score:
                total.wins += 1
            elif score == opponent_score:
                total.draws += 1
            else:
                total.losses += 1
    for team_id, total in totals.items():
        total.elo_score = Decimal(str(round(ratings[team_id], 0)))
    return dict(totals)
