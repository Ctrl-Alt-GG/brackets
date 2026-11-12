from collections import defaultdict

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncConnection

from bracket.models.db.match import Match, MatchWithDetailsDefinitive
from bracket.models.db.util import StageWithStageItems
from bracket.utils.id_types import MatchId


def matches_overlap(match1: Match, match2: Match) -> bool:
    """Whether the two matches are on at the same moment, including their breaks."""
    if match1.start_time is None or match2.start_time is None:
        return False

    return match1.start_time < match2.end_time and match2.start_time < match1.end_time


def get_conflicting_matches(
    stages: list[StageWithStageItems],
) -> tuple[
    defaultdict[MatchId, list[bool]],
    set[MatchId],
]:
    matches = [
        match
        for stage in stages
        for stage_item in stage.stage_items
        for round_ in stage_item.rounds
        for match in round_.matches
        if isinstance(match, MatchWithDetailsDefinitive)
    ]

    conflicts_to_set: defaultdict[MatchId, list[bool]] = defaultdict(lambda: [False, False])
    matches_with_conflicts = set()
    conflicts_to_clear = set()

    for i, match1 in enumerate(matches):
        for match2 in matches[i + 1 :]:
            if match1.id == match2.id:
                continue

            # The same team has a different slot id in each stage item. Compare teams so
            # simultaneous matches in different groups are detected too; open slots have
            # no team and cannot conflict.
            conflicting_team_ids = {
                input_.team_id for input_ in match1.stage_item_inputs if input_.team_id is not None
            } & {
                input_.team_id for input_ in match2.stage_item_inputs if input_.team_id is not None
            }

            if not conflicting_team_ids:
                continue

            if matches_overlap(match1, match2):
                for match in (match1, match2):
                    if not conflicts_to_set[match.id][0]:
                        conflicts_to_set[match.id][0] = (
                            match.stage_item_input1.team_id in conflicting_team_ids
                        )
                    if not conflicts_to_set[match.id][1]:
                        conflicts_to_set[match.id][1] = (
                            match.stage_item_input2.team_id in conflicting_team_ids
                        )

                matches_with_conflicts.add(match1.id)
                matches_with_conflicts.add(match2.id)

    for match in matches:
        if match.id not in matches_with_conflicts:
            conflicts_to_clear.add(match.id)

    assert set(conflicts_to_set.keys()).intersection(conflicts_to_clear) == set()
    return conflicts_to_set, conflicts_to_clear


async def set_conflicts(
    conn: AsyncConnection,
    conflicts_to_set: dict[MatchId, list[bool]],
    conflicts_to_clear: set[MatchId],
) -> None:
    for match_id, conflict in conflicts_to_set.items():
        await conn.execute(
            text(
                """
                UPDATE matches
                SET
                    stage_item_input1_conflict = :conflict1_id,
                    stage_item_input2_conflict = :conflict2_id
                WHERE id = :match_id
                """
            ),
            {
                "match_id": match_id,
                "conflict1_id": conflict[0],
                "conflict2_id": conflict[1],
            },
        )

    for match_id in conflicts_to_clear:
        await conn.execute(
            text(
                """
                UPDATE matches
                SET
                    stage_item_input1_conflict = false,
                    stage_item_input2_conflict = false
                WHERE id = :match_id
                """
            ),
            {"match_id": match_id},
        )


async def handle_conflicts(conn: AsyncConnection, stages: list[StageWithStageItems]) -> None:
    conflicts_to_set, conflicts_to_clear = get_conflicting_matches(stages)
    await set_conflicts(conn, conflicts_to_set, conflicts_to_clear)
