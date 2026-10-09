from pydantic import TypeAdapter
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncConnection

from bracket.models.db.stage_item_inputs import (
    StageItemInput,
    StageItemInputBase,
    StageItemInputCreateBody,
    StageItemInputCreateBodyFinal,
    StageItemInputCreateBodyTentative,
    StageItemInputFinal,
)
from bracket.sql.teams import get_team_by_id
from bracket.utils.id_types import RankingId, StageItemId, StageItemInputId, TeamId, TournamentId


async def get_stage_item_input_by_id(
    conn: AsyncConnection, tournament_id: TournamentId, stage_item_input_id: StageItemInputId
) -> StageItemInput | None:
    query = """
        SELECT *
        FROM stage_item_inputs
        WHERE id = :stage_item_input_id
        AND tournament_id = :tournament_id
    """
    result = (
        await conn.execute(
            text(query),
            {"stage_item_input_id": stage_item_input_id, "tournament_id": tournament_id},
        )
    ).first()
    if result is None:
        return None

    if result.team_id is not None:
        data = dict(result._mapping)
        data["team"] = await get_team_by_id(conn, data["team_id"], tournament_id)
        return StageItemInputFinal.model_validate(data)

    return TypeAdapter(StageItemInput).validate_python(dict(result._mapping))


async def get_stage_item_ids_by_ranking_id(
    conn: AsyncConnection, tournament_id: TournamentId, ranking_id: RankingId
) -> list[StageItemId]:
    query = """
        SELECT stage_items.id
        FROM stage_items
        JOIN stages ON stages.id = stage_items.stage_id
        WHERE stage_items.ranking_id = :ranking_id
        AND stages.tournament_id = :tournament_id
    """
    results = await conn.execute(
        text(query), {"ranking_id": ranking_id, "tournament_id": tournament_id}
    )
    return [StageItemId(result.id) for result in results]


async def sql_set_team_id_for_stage_item_input(
    conn: AsyncConnection,
    tournament_id: TournamentId,
    stage_item_input_id: StageItemInputId,
    team_id: TeamId | None,
) -> None:
    query = """
        UPDATE stage_item_inputs
        SET team_id = :team_id
        WHERE tournament_id = :tournament_id
        AND stage_item_inputs.id = :stage_item_input_id
        """
    await conn.execute(
        text(query),
        {
            "team_id": team_id,
            "stage_item_input_id": stage_item_input_id,
            "tournament_id": tournament_id,
        },
    )


async def sql_delete_stage_item_inputs(conn: AsyncConnection, stage_item_id: StageItemId) -> None:
    query = """
        DELETE FROM stage_item_inputs
        WHERE stage_item_id = :stage_item_id OR winner_from_stage_item_id = :stage_item_id
        """
    await conn.execute(text(query), {"stage_item_id": stage_item_id})


async def sql_create_stage_item_input(
    conn: AsyncConnection,
    tournament_id: TournamentId,
    stage_item_id: StageItemId,
    stage_item_input: StageItemInputCreateBody,
) -> StageItemInputBase:
    query = """
        INSERT INTO stage_item_inputs
        (
            slot,
            tournament_id,
            stage_item_id,
            team_id,
            winner_from_stage_item_id,
            winner_position
        )
        VALUES
        (
            :slot,
            :tournament_id,
            :stage_item_id,
            :team_id,
            :winner_from_stage_item_id,
            :winner_position
        )
        RETURNING *
        """
    result = (
        await conn.execute(
            text(query),
            {
                "slot": stage_item_input.slot,
                "tournament_id": tournament_id,
                "stage_item_id": stage_item_id,
                "team_id": (
                    stage_item_input.team_id
                    if isinstance(stage_item_input, StageItemInputCreateBodyFinal)
                    else None
                ),
                "winner_from_stage_item_id": (
                    stage_item_input.winner_from_stage_item_id
                    if isinstance(stage_item_input, StageItemInputCreateBodyTentative)
                    else None
                ),
                "winner_position": (
                    stage_item_input.winner_position
                    if isinstance(stage_item_input, StageItemInputCreateBodyTentative)
                    else None
                ),
            },
        )
    ).first()

    if result is None:
        raise ValueError("Could not create stage")

    return StageItemInputBase.model_validate(result._mapping)
