"""The results of every team over the whole tournament."""

from collections import defaultdict
from collections.abc import Iterable, Mapping
from decimal import Decimal

from sqlalchemy.ext.asyncio import AsyncSession

from bracket.logic.ranking.elo import K, expected_result
from bracket.logic.tournament_graph import TournamentGraph
from bracket.models.db.participation import TournamentTeam
from bracket.models.db.stage_item_inputs import StageItemInputFinal
from bracket.models.results import START_ELO, ResultTotals, TeamMatchResult
from bracket.sql.matches import get_played_team_results
from bracket.utils.id_types import TeamId, TournamentId

# A team's rating keeps one decimal place in answers, also before the team has played.
NO_RESULTS = ResultTotals(elo_score=Decimal("1200.0"))


def determine_team_totals(results: Iterable[TeamMatchResult]) -> dict[TeamId, ResultTotals]:
    """
    Replay the results in order. Every result moves both teams' ratings by how far it is from the
    expected one, which follows from their ratings before the match.
    """
    totals: defaultdict[TeamId, ResultTotals] = defaultdict(ResultTotals)
    ratings: defaultdict[TeamId, float] = defaultdict(lambda: float(START_ELO))
    for result in results:
        team_ids = (result.team1_id, result.team2_id)
        scores = (result.score1, result.score2)
        before = (ratings[team_ids[0]], ratings[team_ids[1]])
        for index, team_id in enumerate(team_ids):
            score, opponent_score = scores[index], scores[1 - index]
            outcome = 1.0 if score > opponent_score else 0.5 if score == opponent_score else 0.0
            ratings[team_id] += K * (outcome - expected_result(before[index], before[1 - index]))
            total = totals[team_id]
            total.swiss_score += Decimal(str(outcome))
            if score > opponent_score:
                total.wins += 1
            elif score == opponent_score:
                total.draws += 1
            else:
                total.losses += 1
    for team_id, total in totals.items():
        total.elo_score = Decimal(str(round(ratings[team_id], 0)))
    return dict(totals)


async def get_team_totals(
    session: AsyncSession, tournament_id: TournamentId
) -> dict[TeamId, ResultTotals]:
    """Replay the published results in schedule order, including corrections and deletions."""
    return determine_team_totals(await get_played_team_results(session, tournament_id))


def with_totals[TeamT: TournamentTeam](team: TeamT, totals: Mapping[TeamId, ResultTotals]) -> TeamT:
    """The team with its results in the tournament, replayed from the matches."""
    return team.model_copy(update=totals.get(team.id, NO_RESULTS).model_dump())


async def add_team_totals(
    session: AsyncSession,
    tournament_id: TournamentId,
    graph: TournamentGraph,
    *,
    totals: Mapping[TeamId, ResultTotals] | None = None,
) -> None:
    """Give every team in the slots of the loaded stages its replayed results."""
    slots = [slot for slot in graph.slots() if isinstance(slot, StageItemInputFinal)]
    if not slots:
        return
    if totals is None:
        totals = await get_team_totals(session, tournament_id)
    graph.replace_slots(
        {
            slot.id: slot.model_copy(update={"team": with_totals(slot.team, totals)})
            for slot in slots
        }
    )
