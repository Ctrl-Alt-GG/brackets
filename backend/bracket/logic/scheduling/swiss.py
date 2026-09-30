import random
from collections import Counter
from typing import NamedTuple

import networkx as nx

from bracket.models.db.match import MatchWithDetailsDefinitive
from bracket.models.db.stage_item_inputs import StageItemInputFinal
from bracket.models.db.util import StageItemWithRounds
from bracket.utils.id_types import StageItemInputId

# Placeholder opponent of the team that sits out. Database ids are positive, so it can't clash.
BYE = StageItemInputId(-1)


class SwissPairing(NamedTuple):
    pairs: list[tuple[StageItemInputFinal, StageItemInputFinal]]
    unpaired: list[StageItemInputFinal]


def get_active_teams(stage_item: StageItemWithRounds) -> list[StageItemInputFinal]:
    return [
        input_
        for input_ in stage_item.inputs
        if isinstance(input_, StageItemInputFinal) and input_.team.active
    ]


def get_swiss_pairing(
    stage_item: StageItemWithRounds, rng: random.Random | None = None
) -> SwissPairing:
    """
    Pair the active teams of a Swiss stage item for its next round.

    Pairing is a maximum weight matching on the graph of pairs that haven't played each other yet,
    so as many teams as possible get an opponent and no pair meets twice. Among those pairings,
    the one that sits out (when the number of teams is odd) is the lowest ranked team that hasn't
    sat out before, and the teams are paired with opponents as close to them in the standings as
    possible. Teams with equal standings are paired in random order.
    """
    teams = get_active_teams(stage_item)
    played_pairs: set[frozenset[StageItemInputId]] = set()
    times_played: Counter[StageItemInputId] = Counter()

    for round_ in stage_item.rounds:
        for match in round_.matches:
            if isinstance(match, MatchWithDetailsDefinitive):
                played_pairs.add(frozenset(match.stage_item_input_ids))
                times_played.update(match.stage_item_input_ids)

    (rng or random.Random()).shuffle(teams)
    # Highest ranked first; the shuffle above decides between teams with equal points.
    teams.sort(key=lambda team: team.points, reverse=True)

    # Weights are integers so that networkx computes the matching exactly. Pairing teams far apart
    # in the standings costs quadratically more, and choosing who sits out outweighs any pairing.
    def gap(team1: StageItemInputFinal, team2: StageItemInputFinal) -> int:
        return int(abs(team1.points - team2.points)) ** 2

    max_gap = gap(teams[0], teams[-1]) if len(teams) > 0 else 0
    max_total_pair_weight = (len(teams) // 2) * (max_gap + 1)
    most_played = max((times_played[team.id] for team in teams), default=0)

    graph: nx.Graph[StageItemInputId] = nx.Graph()
    graph.add_nodes_from(team.id for team in teams)
    for index, team in enumerate(teams):
        for opponent in teams[index + 1 :]:
            if frozenset((team.id, opponent.id)) not in played_pairs:
                graph.add_edge(team.id, opponent.id, weight=max_gap - gap(team, opponent) + 1)

    if len(teams) % 2 == 1:
        for rank, team in enumerate(teams):
            hasnt_sat_out = times_played[team.id] == most_played
            graph.add_edge(
                team.id,
                BYE,
                weight=(max_total_pair_weight + 1) * (len(teams) * hasnt_sat_out + rank + 1),
            )

    matching = nx.max_weight_matching(graph, maxcardinality=True)

    rank_by_id = {team.id: rank for rank, team in enumerate(teams)}
    teams_by_id = {team.id: team for team in teams}
    pair_ids = sorted(
        (
            (id1, id2) if rank_by_id[id1] < rank_by_id[id2] else (id2, id1)
            for id1, id2 in matching
            if BYE not in (id1, id2)
        ),
        key=lambda pair: rank_by_id[pair[0]],
    )
    paired_ids = {team_id for pair in pair_ids for team_id in pair}
    return SwissPairing(
        pairs=[(teams_by_id[id1], teams_by_id[id2]) for id1, id2 in pair_ids],
        unpaired=[team for team in teams if team.id not in paired_ids],
    )
