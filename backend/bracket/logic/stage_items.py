"""Stage items: the groups, brackets and Swiss stages within a stage, and their slots."""

from fastapi import HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from starlette import status

from bracket import orm
from bracket.logic.planning.matches import schedule_all_matches
from bracket.logic.ranking.calculation import recalculate_ranking_for_stage_item
from bracket.logic.ranking.elimination import update_inputs_in_complete_elimination_stage_item
from bracket.logic.scheduling.builder import build_matches_for_stage_item, get_stage_format
from bracket.logic.subscriptions import Limit, check_requirement
from bracket.logic.tournament_graph import TournamentGraph
from bracket.models.db.match import is_played
from bracket.models.db.stage_item import StageItemCreateBody
from bracket.models.db.stage_item_inputs import (
    StageItemInputUpdateBody,
    StageItemInputUpdateBodyTentative,
)
from bracket.models.db.stage_tree import StageItemWithRounds
from bracket.models.db.user import UserPublic
from bracket.models.enums import StageType
from bracket.sql.stage_item_inputs import get_stage_item_input_by_id, sql_update_stage_item_input
from bracket.sql.stage_items import (
    sql_create_stage_item_with_empty_inputs,
    sql_delete_stage_item,
    sql_update_stage_item_name,
)
from bracket.sql.stages import get_full_tournament_details
from bracket.sql.tournaments import count_tournament_records
from bracket.sql.validation import validate_stage_item_create, validate_stage_item_input_update
from bracket.utils.errors import (
    ForeignKey,
    UniqueIndex,
    check_foreign_key_violation,
    check_unique_constraint_violation,
)
from bracket.utils.i18n import gettext
from bracket.utils.id_types import StageItemId, StageItemInputId, TournamentId


async def create_stage_item(
    session: AsyncSession,
    tournament_id: TournamentId,
    body: StageItemCreateBody,
    user: UserPublic,
) -> None:
    """
    Create a stage item with the rounds and matches of its format. Those rounds count towards the
    tournament's limit, so a stage item that would exceed it isn't created at all.
    """
    await validate_stage_item_create(session, tournament_id, body)
    check_requirement(
        Limit.STAGE_ITEMS,
        await count_tournament_records(session, orm.StageItem, tournament_id),
        user,
    )
    check_requirement(
        Limit.ROUNDS,
        await count_tournament_records(session, orm.Round, tournament_id),
        user,
        additions=get_stage_format(body.type, body.team_count).rounds,
    )

    stage_item = await sql_create_stage_item_with_empty_inputs(session, tournament_id, body)
    await build_matches_for_stage_item(session, stage_item, tournament_id)
    await schedule_all_matches(session, tournament_id)


async def rename_stage_item(
    session: AsyncSession, tournament_id: TournamentId, stage_item: StageItemWithRounds, name: str
) -> None:
    await sql_update_stage_item_name(session, stage_item.id, name)
    await recalculate_ranking_for_stage_item(session, tournament_id, stage_item)
    if stage_item.type is StageType.SINGLE_ELIMINATION:
        graph = TournamentGraph(
            await get_full_tournament_details(
                session, tournament_id, stage_item_ids={stage_item.id}
            )
        )
        await update_inputs_in_complete_elimination_stage_item(
            session, graph, graph.stage_item(stage_item.id)
        )


async def delete_stage_item(
    session: AsyncSession, tournament_id: TournamentId, stage_item_id: StageItemId
) -> None:
    """
    Delete a stage item with its rounds and matches.

    Slots of later stage items that take a team from it become open again. That is refused
    once such a stage item has results, which belong to the teams that advanced.
    """
    stages = await get_full_tournament_details(session, tournament_id)
    fed_with_results = sorted(
        {
            stage_item.label
            for stage in stages
            for stage_item in stage.stage_items
            if any(
                input_.winner_from_stage_item_id == stage_item_id for input_ in stage_item.inputs
            )
            and any(is_played(match) for round_ in stage_item.rounds for match in round_.matches)
        }
    )
    if fed_with_results:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=gettext(
                "{items} takes teams from this stage item and already has results. Delete it "
                "first.",
                items=", ".join(fed_with_results),
            ),
        )

    await sql_delete_stage_item(session, stage_item_id)
    await schedule_all_matches(session, tournament_id)


async def update_stage_item_input(
    session: AsyncSession,
    tournament_id: TournamentId,
    stage_item: StageItemWithRounds,
    stage_item_input_id: StageItemInputId,
    body: StageItemInputUpdateBody,
) -> None:
    """Change what fills a slot: a team, a place of an earlier stage item, or nothing."""
    stage_item_input = await get_stage_item_input_by_id(session, tournament_id, stage_item_input_id)
    await validate_stage_item_input_update(
        session, tournament_id, stage_item_input, body, stage_item
    )
    assert stage_item_input is not None
    if isinstance(body, StageItemInputUpdateBodyTentative):
        unchanged = (
            stage_item_input.winner_from_stage_item_id == body.winner_from_stage_item_id
            and stage_item_input.winner_position == body.winner_position
        )
    else:
        unchanged = (
            stage_item_input.team_id == body.team_id
            and stage_item_input.winner_from_stage_item_id is None
        )
    if unchanged:
        return
    if any(
        is_played(match)
        and stage_item_input_id in (match.stage_item_input1_id, match.stage_item_input2_id)
        for round_ in stage_item.rounds
        for match in round_.matches
    ):
        raise HTTPException(
            400,
            gettext(
                "Clear this team's match results in Rounds before changing its slot. "
                "Recorded results must stay with the teams that played them."
            ),
        )

    with (
        check_unique_constraint_violation(
            {
                UniqueIndex.stage_item_inputs_stage_item_id_team_id_key,
                UniqueIndex.stage_item_inputs_stage_item_id_winner_from_stage_item_id_w_key,
            },
        ),
        check_foreign_key_violation({ForeignKey.stage_item_inputs_team_id_fkey}),
    ):
        await sql_update_stage_item_input(
            session, tournament_id, stage_item.id, stage_item_input_id, body
        )

    graph = TournamentGraph(await get_full_tournament_details(session, tournament_id))
    await recalculate_ranking_for_stage_item(
        session, tournament_id, graph.stage_item(stage_item.id)
    )
    # The slot's team may play elsewhere at the times its matches were planned for.
    await schedule_all_matches(session, tournament_id, graph=graph)
