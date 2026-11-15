import math
from collections import defaultdict
from decimal import Decimal

from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import aliased

from bracket import orm
from bracket.logic.ranking.statistics import START_ELO, D, K, TeamTotals
from bracket.utils.id_types import TeamId, TournamentId


async def get_team_totals(
    session: AsyncSession, tournament_id: TournamentId
) -> dict[TeamId, TeamTotals]:
    """Replay published results in schedule order, including corrections and deletions.

    Read the small match projection directly so team totals can also enrich embedded teams in
    stage responses without recursing through the full stage loader.
    """
    input1, input2 = aliased(orm.StageItemInput), aliased(orm.StageItemInput)
    rows = await session.execute(
        select(
            input1.team_id.label("team1"),
            input2.team_id.label("team2"),
            orm.Match.stage_item_input1_score.label("score1"),
            orm.Match.stage_item_input2_score.label("score2"),
        )
        .select_from(orm.Match)
        .join(orm.Round, orm.Round.id == orm.Match.round_id)
        .join(orm.StageItem, orm.StageItem.id == orm.Round.stage_item_id)
        .join(orm.Stage, orm.Stage.id == orm.StageItem.stage_id)
        .join(
            input1,
            (input1.id == orm.Match.stage_item_input1_id)
            & (input1.stage_item_id == orm.StageItem.id),
        )
        .join(
            input2,
            (input2.id == orm.Match.stage_item_input2_id)
            & (input2.stage_item_id == orm.StageItem.id),
        )
        .where(
            orm.Stage.tournament_id == tournament_id,
            orm.Round.is_draft.is_(False),
            input1.team_id.is_not(None),
            input2.team_id.is_not(None),
            input1.team_id != input2.team_id,
            or_(
                orm.Match.stage_item_input1_score != 0,
                orm.Match.stage_item_input2_score != 0,
                orm.Match.scoreless_result,
            ),
        )
        .order_by(orm.Match.start_time.asc().nulls_last(), orm.Round.id, orm.Match.id)
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
