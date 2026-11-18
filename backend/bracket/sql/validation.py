from typing import NoReturn

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from bracket import orm
from bracket.models.db.match import MatchCreateBodyFrontend
from bracket.models.db.round import Round, RoundCreateBody
from bracket.models.db.stage_item import StageItem, StageItemCreateBody
from bracket.models.db.stage_item_inputs import (
    StageItemInput,
    StageItemInputUpdateBody,
    StageItemInputUpdateBodyFinal,
    StageItemInputUpdateBodyTentative,
)
from bracket.models.enums import StageType
from bracket.utils.id_types import PlayerId, TournamentId


def _missing_reference(kind: str, value: object) -> NoReturn:
    raise HTTPException(400, f"Could not find {kind}(s) with ID {value}")


async def validate_player_ids(
    session: AsyncSession, tournament_id: TournamentId, player_ids: set[PlayerId]
) -> None:
    if not player_ids:
        return
    found = set(
        await session.scalars(
            select(orm.Player.id).where(
                orm.Player.tournament_id == tournament_id, orm.Player.id.in_(player_ids)
            )
        )
    )
    if found != player_ids:
        _missing_reference("Player", player_ids)


async def validate_stage_item_create(
    session: AsyncSession, tournament_id: TournamentId, body: StageItemCreateBody
) -> None:
    stage_id = await session.scalar(
        select(orm.Stage.id).where(
            orm.Stage.id == body.stage_id, orm.Stage.tournament_id == tournament_id
        )
    )
    if stage_id is None:
        _missing_reference("Stage", body.stage_id)
    if body.ranking_id is not None:
        ranking_id = await session.scalar(
            select(orm.Ranking.id).where(
                orm.Ranking.id == body.ranking_id, orm.Ranking.tournament_id == tournament_id
            )
        )
        if ranking_id is None:
            _missing_reference("Ranking", body.ranking_id)


async def validate_round_create(
    session: AsyncSession, tournament_id: TournamentId, body: RoundCreateBody
) -> None:
    item_id = await session.scalar(
        select(orm.StageItem.id).where(
            orm.StageItem.id == body.stage_item_id, orm.StageItem.tournament_id == tournament_id
        )
    )
    if item_id is None:
        _missing_reference("StageItem", body.stage_item_id)


async def validate_match_create(
    session: AsyncSession, tournament_id: TournamentId, body: MatchCreateBodyFrontend
) -> Round:
    round_ = await session.scalar(
        select(orm.Round)
        .where(orm.Round.id == body.round_id, orm.Round.tournament_id == tournament_id)
        .execution_options(populate_existing=True)
    )
    if round_ is None:
        _missing_reference("Round", body.round_id)
    input_ids = [body.stage_item_input1_id, body.stage_item_input2_id]
    requested_inputs = {id_ for id_ in input_ids if id_ is not None}
    if requested_inputs:
        found_inputs = set(
            await session.scalars(
                select(orm.StageItemInput.id).where(
                    orm.StageItemInput.tournament_id == tournament_id,
                    orm.StageItemInput.id.in_(requested_inputs),
                )
            )
        )
        for input_id in input_ids:
            if input_id is not None and input_id not in found_inputs:
                _missing_reference("StageItemInput", input_id)
    winner_ids = [
        body.stage_item_input1_winner_from_match_id,
        body.stage_item_input2_winner_from_match_id,
    ]
    requested_winners = {id_ for id_ in winner_ids if id_ is not None}
    if requested_winners:
        found_winners = set(
            await session.scalars(
                select(orm.Match.id).where(
                    orm.Match.tournament_id == tournament_id, orm.Match.id.in_(requested_winners)
                )
            )
        )
        for match_id in winner_ids:
            if match_id is not None and match_id not in found_winners:
                _missing_reference("Match", match_id)
    return Round.model_validate(round_)


async def validate_stage_item_input_update(
    session: AsyncSession,
    tournament_id: TournamentId,
    current: StageItemInput | None,
    body: StageItemInputUpdateBody,
    target: StageItem,
) -> None:
    if current is None or current.stage_item_id != target.id:
        raise HTTPException(404, "Could not find the stage item input")
    if isinstance(body, StageItemInputUpdateBodyTentative):
        source = await session.scalar(
            select(orm.StageItem).where(
                orm.StageItem.id == body.winner_from_stage_item_id,
                orm.StageItem.tournament_id == tournament_id,
            )
        )
        if source is None:
            raise HTTPException(
                404, f"Could not find stage item with id {body.winner_from_stage_item_id}"
            )
        if source.stage_id >= target.stage_id or source.type is StageType.SINGLE_ELIMINATION:
            raise HTTPException(400, "Choose a group or Swiss stage item from an earlier stage")
        if body.winner_position > source.team_count:
            raise HTTPException(400, "The source stage item doesn't have that many team slots")
    elif isinstance(body, StageItemInputUpdateBodyFinal):
        team_id = await session.scalar(
            select(orm.Team.id).where(
                orm.Team.id == body.team_id, orm.Team.tournament_id == tournament_id
            )
        )
        if team_id is None:
            raise HTTPException(404, f"Could not find team with id {body.team_id}")
