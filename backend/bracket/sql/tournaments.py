from typing import Any, Literal

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncConnection

from bracket.models.db.tournament import (
    Tournament,
    TournamentBody,
    TournamentChangeStatusBody,
    TournamentUpdateBody,
)
from bracket.utils.id_types import TournamentId


async def sql_get_tournament(conn: AsyncConnection, tournament_id: TournamentId) -> Tournament:
    query = """
        SELECT *
        FROM tournaments
        WHERE id = :tournament_id
        """
    result = await conn.execute(text(query), {"tournament_id": tournament_id})
    return Tournament.model_validate(result.one()._mapping)


async def sql_get_tournament_by_endpoint_name(
    conn: AsyncConnection, endpoint_name: str
) -> Tournament | None:
    query = """
        SELECT *
        FROM tournaments
        WHERE dashboard_endpoint = :endpoint_name
        AND dashboard_public IS TRUE
        """
    result = (await conn.execute(text(query), {"endpoint_name": endpoint_name})).first()
    return Tournament.model_validate(result._mapping) if result is not None else None


async def sql_get_tournaments(
    conn: AsyncConnection,
    club_ids: tuple[int, ...],
    endpoint_name: str | None = None,
    filter_: Literal["ALL", "OPEN", "ARCHIVED"] = "ALL",
) -> list[Tournament]:
    query = """
        SELECT *
        FROM tournaments
        WHERE club_id = any(:club_ids)
        """

    params: dict[str, Any] = {"club_ids": club_ids}

    if endpoint_name is not None:
        query += " AND dashboard_endpoint = :endpoint_name"
        params["endpoint_name"] = endpoint_name

    if filter_ != "ALL":
        query += " AND status = :status"
        params["status"] = filter_

    result = await conn.execute(text(query), params)
    return [Tournament.model_validate(x._mapping) for x in result]


async def sql_get_public_tournaments(
    conn: AsyncConnection,
    filter_: Literal["ALL", "OPEN", "ARCHIVED"] = "OPEN",
) -> list[Tournament]:
    # Same rule as `user_authenticated_or_public_dashboard`: open tournaments are visible to
    # everyone, archived ones only when their dashboard is public.
    query = """
        SELECT *
        FROM tournaments
        WHERE (status = 'OPEN' OR dashboard_public IS TRUE)
        """
    params: dict[str, Any] = {}

    if filter_ != "ALL":
        query += " AND status = :status"
        params["status"] = filter_

    # Running tournaments first, then the most recent ones.
    query += " ORDER BY status = 'ARCHIVED', start_time DESC"

    result = await conn.execute(text(query), params)
    return [Tournament.model_validate(x._mapping) for x in result]


async def sql_delete_tournament(conn: AsyncConnection, tournament_id: TournamentId) -> None:
    query = """
        DELETE FROM tournaments
        WHERE id = :tournament_id
        """
    await conn.execute(text(query), {"tournament_id": tournament_id})


async def sql_update_tournament(
    conn: AsyncConnection, tournament_id: TournamentId, tournament: TournamentUpdateBody
) -> None:
    query = """
        UPDATE tournaments
        SET
            start_time = :start_time,
            name = :name,
            dashboard_public = :dashboard_public,
            dashboard_endpoint = :dashboard_endpoint,
            players_can_be_in_multiple_teams = :players_can_be_in_multiple_teams,
            duration_minutes = :duration_minutes,
            margin_minutes = :margin_minutes
        WHERE tournaments.id = :tournament_id
        """
    await conn.execute(
        text(query), {"tournament_id": tournament_id, **tournament.model_dump(exclude_none=False)}
    )


async def sql_update_tournament_status(
    conn: AsyncConnection, tournament_id: TournamentId, body: TournamentChangeStatusBody
) -> None:
    # The public dashboard setting is left alone, so a public tournament stays public once
    # archived and its results remain available.
    query = """
        UPDATE tournaments
        SET status = :state
        WHERE tournaments.id = :tournament_id
        """
    await conn.execute(text(query), {"tournament_id": tournament_id, "state": body.status.value})


async def sql_create_tournament(conn: AsyncConnection, tournament: TournamentBody) -> TournamentId:
    query = """
        INSERT INTO tournaments (
            name,
            start_time,
            club_id,
            dashboard_public,
            dashboard_endpoint,
            players_can_be_in_multiple_teams,
            duration_minutes,
            margin_minutes
        )
        VALUES (
            :name,
            :start_time,
            :club_id,
            :dashboard_public,
            :dashboard_endpoint,
            :players_can_be_in_multiple_teams,
            :duration_minutes,
            :margin_minutes
        )
        RETURNING id
        """
    return TournamentId(await conn.scalar(text(query), tournament.model_dump(exclude_none=False)))
