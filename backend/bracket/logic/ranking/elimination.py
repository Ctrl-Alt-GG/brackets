from sqlalchemy.ext.asyncio import AsyncConnection

from bracket.models.db.match import Match
from bracket.models.db.stage_item_inputs import StageItemInput
from bracket.models.db.util import StageItemWithRounds
from bracket.sql.matches import (
    sql_set_input_ids_for_match,
)
from bracket.utils.id_types import (
    MatchId,
    RoundId,
)


def get_inputs_to_update_in_subsequent_elimination_rounds(
    current_round_id: RoundId,
    stage_item: StageItemWithRounds,
    match_ids: set[MatchId] | None = None,
) -> dict[MatchId, Match]:
    """
    Determine the updates of stage item input IDs in the elimination tree.

    Crucial aspect is that entering a winner for a match will influence matches of subsequent
    rounds, because of the tree-like structure of elimination stage items.

    With `match_ids`, only the matches of the current round that changed are followed down the
    tree. Without them, every match of the tree after the current round is worked out again.

    A match whose competitors change loses its result: that result was between other teams. Its
    own winner is undecided again, which in turn empties the slot it fed.
    """
    rounds = sorted(stage_item.rounds, key=lambda round_: round_.id)
    current_round = next(round_ for round_ in rounds if round_.id == current_round_id)
    known_matches: dict[MatchId, Match] = {
        match.id: match
        for match in current_round.matches
        if match_ids is None or match.id in match_ids
    }
    updates: dict[MatchId, Match] = {}

    for round_ in rounds:
        if round_.id <= current_round.id:
            continue

        for subsequent_match in round_.matches:
            updated_inputs: list[StageItemInput | None] = [
                subsequent_match.stage_item_input1,
                subsequent_match.stage_item_input2,
            ]
            original_inputs = updated_inputs.copy()

            for index, source_match_id in enumerate(
                (
                    subsequent_match.stage_item_input1_winner_from_match_id,
                    subsequent_match.stage_item_input2_winner_from_match_id,
                )
            ):
                if source_match_id is not None and (
                    source_match := known_matches.get(source_match_id)
                ):
                    updated_inputs[index] = source_match.get_winner()

            if original_inputs != updated_inputs:
                input_ids = [input_.id if input_ else None for input_ in updated_inputs]
                updated_match = subsequent_match.model_copy(
                    update={
                        "stage_item_input1_id": input_ids[0],
                        "stage_item_input2_id": input_ids[1],
                        "stage_item_input1": updated_inputs[0],
                        "stage_item_input2": updated_inputs[1],
                        "stage_item_input1_score": 0,
                        "stage_item_input2_score": 0,
                        "scoreless_result": False,
                    }
                )
                updates[subsequent_match.id] = updated_match
                known_matches[subsequent_match.id] = updated_match
            elif match_ids is None:
                known_matches[subsequent_match.id] = subsequent_match

    return updates


async def update_inputs_in_subsequent_elimination_rounds(
    conn: AsyncConnection,
    current_round_id: RoundId,
    stage_item: StageItemWithRounds,
    match_ids: set[MatchId] | None = None,
) -> None:
    updates = get_inputs_to_update_in_subsequent_elimination_rounds(
        current_round_id, stage_item, match_ids
    )
    for match in updates.values():
        await sql_set_input_ids_for_match(
            conn,
            match.round_id,
            match.id,
            [match.stage_item_input1_id, match.stage_item_input2_id],
            reset_result=True,
        )


async def update_inputs_in_complete_elimination_stage_item(
    conn: AsyncConnection,
    stage_item: StageItemWithRounds,
) -> None:
    """Work out every slot of the bracket again, starting from the results of the first round."""
    if len(stage_item.rounds) < 1:
        return

    first_round = min(stage_item.rounds, key=lambda round_: round_.id)
    await update_inputs_in_subsequent_elimination_rounds(conn, first_round.id, stage_item)
