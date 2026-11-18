import heapq
from collections import defaultdict
from itertools import count

from heliclockter import datetime_utc
from sqlalchemy.ext.asyncio import AsyncSession
from starlette.concurrency import run_in_threadpool

from bracket.logic.tournament_graph import TournamentGraph
from bracket.models.db.match import Match
from bracket.models.db.stage_item_inputs import StageItemInput
from bracket.models.db.stage_tree import StageWithStageItems
from bracket.sql.matches import sql_update_match_conflicts
from bracket.utils.id_types import MatchId, TeamId

ConflictFlags = tuple[bool, bool]


def matches_overlap(match1: Match, match2: Match) -> bool:
    """Whether the two matches are on at the same moment, including their breaks."""
    if match1.start_time is None or match2.start_time is None:
        return False

    return match1.start_time < match2.end_time and match2.start_time < match1.end_time


def _team_id(stage_item_input: StageItemInput | None) -> TeamId | None:
    return stage_item_input.team_id if stage_item_input is not None else None


def _all_matches(stages: list[StageWithStageItems]) -> list[Match]:
    return [
        match
        for stage in stages
        for stage_item in stage.stage_items
        for round_ in stage_item.rounds
        for match in round_.matches
    ]


def overlapping_matches(team_matches: list[Match]) -> set[MatchId]:
    """
    Those of a team's matches that are on at the same moment as another one of them.

    The matches are swept in the order they start, keeping those that haven't ended yet. A match
    overlaps exactly the ones still going when it starts. Every match is marked once, however many
    matches it overlaps.
    """
    timed = sorted(
        ((match.start_time, match) for match in team_matches if match.start_time is not None),
        key=lambda timed_match: timed_match[0],
    )
    order = count()
    # The matches that haven't ended yet, by when they end.
    ongoing: list[tuple[datetime_utc, int, Match]] = []
    # The ongoing matches that aren't marked yet.
    unmarked: list[Match] = []
    overlapping: set[MatchId] = set()
    for start, match in timed:
        while ongoing and ongoing[0][0] <= start:
            heapq.heappop(ongoing)
        if ongoing:
            overlapping.add(match.id)
            overlapping.update(other.id for other in unmarked if other.end_time > start)
            unmarked.clear()
        if match.id not in overlapping:
            unmarked.append(match)
        heapq.heappush(ongoing, (match.end_time, next(order), match))
    return overlapping


def get_conflicting_matches(stages: list[StageWithStageItems]) -> dict[MatchId, ConflictFlags]:
    """
    For every match, whether each of its two teams plays another match at the same time.

    A team has a different slot in every stage item, so matches are compared by team, which also
    finds simultaneous matches in different groups. A slot without a team can't conflict. Only
    the matches of one team are compared with each other, rather than every pair of matches.
    """
    matches = _all_matches(stages)
    matches_per_team: defaultdict[TeamId, list[Match]] = defaultdict(list)
    for match in matches:
        for team_id in {_team_id(match.stage_item_input1), _team_id(match.stage_item_input2)}:
            if team_id is not None:
                matches_per_team[team_id].append(match)

    conflicting_teams: defaultdict[MatchId, set[TeamId]] = defaultdict(set)
    for team_id, team_matches in matches_per_team.items():
        for match_id in overlapping_matches(team_matches):
            conflicting_teams[match_id].add(team_id)

    return {
        match.id: (
            _team_id(match.stage_item_input1) in conflicting_teams[match.id],
            _team_id(match.stage_item_input2) in conflicting_teams[match.id],
        )
        for match in matches
    }


async def handle_conflicts(session: AsyncSession, graph: TournamentGraph) -> None:
    """Store only changed conflict flags in one batch, and in the graph."""
    conflicts = await run_in_threadpool(get_conflicting_matches, graph.stages)
    changes = [
        (match.id, *conflicts[match.id])
        for match in graph.matches()
        if (match.stage_item_input1_conflict, match.stage_item_input2_conflict)
        != conflicts[match.id]
    ]
    await sql_update_match_conflicts(session, changes)
    for match_id, conflict1, conflict2 in changes:
        graph.update_match(
            match_id, stage_item_input1_conflict=conflict1, stage_item_input2_conflict=conflict2
        )
