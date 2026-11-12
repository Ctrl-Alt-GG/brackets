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

# A tournament with how far its published matches have got, which tells a running tournament from
# one that is over but hasn't been archived.
TOURNAMENTS_WITH_PROGRESS = """
    SELECT
        tournaments.*,
        COALESCE(progress.matches_total, 0) AS matches_total,
        COALESCE(progress.matches_played, 0) AS matches_played,
        progress.last_match_end
    FROM tournaments
    LEFT JOIN (
        SELECT
            stages.tournament_id,
            count(*) AS matches_total,
            count(*) FILTER (
                WHERE matches.stage_item_input1_score <> 0
                OR matches.stage_item_input2_score <> 0
                OR matches.scoreless_result
            ) AS matches_played,
            max(
                matches.start_time + make_interval(
                    mins => COALESCE(matches.duration_minutes, 0)
                    + COALESCE(matches.margin_minutes, 0)
                )
            ) AS last_match_end
        FROM matches
        JOIN rounds ON rounds.id = matches.round_id
        JOIN stage_items ON stage_items.id = rounds.stage_item_id
        JOIN stages ON stages.id = stage_items.stage_id
        WHERE rounds.is_draft IS FALSE
        GROUP BY stages.tournament_id
    ) AS progress ON progress.tournament_id = tournaments.id
    """

# Running tournaments first, then the most recent ones.
TOURNAMENT_ORDER = """
    ORDER BY tournaments.status = 'ARCHIVED', tournaments.start_time DESC, tournaments.id
    """


async def sql_get_tournament(conn: AsyncConnection, tournament_id: TournamentId) -> Tournament:
    query = f"""
        {TOURNAMENTS_WITH_PROGRESS}
        WHERE tournaments.id = :tournament_id
        """
    result = await conn.execute(text(query), {"tournament_id": tournament_id})
    return Tournament.model_validate(result.one()._mapping)


async def sql_get_tournament_by_endpoint_name(
    conn: AsyncConnection, endpoint_name: str
) -> Tournament | None:
    query = f"""
        {TOURNAMENTS_WITH_PROGRESS}
        WHERE tournaments.dashboard_endpoint = :endpoint_name
        AND tournaments.dashboard_public IS TRUE
        """
    result = (await conn.execute(text(query), {"endpoint_name": endpoint_name})).first()
    return Tournament.model_validate(result._mapping) if result is not None else None


async def sql_get_tournaments(
    conn: AsyncConnection,
    club_ids: tuple[int, ...],
    endpoint_name: str | None = None,
    filter_: Literal["ALL", "OPEN", "ARCHIVED"] = "ALL",
) -> list[Tournament]:
    query = f"""
        {TOURNAMENTS_WITH_PROGRESS}
        WHERE tournaments.club_id = any(:club_ids)
        """

    params: dict[str, Any] = {"club_ids": club_ids}

    if endpoint_name is not None:
        query += " AND tournaments.dashboard_endpoint = :endpoint_name"
        params["endpoint_name"] = endpoint_name

    if filter_ != "ALL":
        query += " AND tournaments.status = :status"
        params["status"] = filter_

    result = await conn.execute(text(query + TOURNAMENT_ORDER), params)
    return [Tournament.model_validate(x._mapping) for x in result]


async def sql_get_public_tournaments(
    conn: AsyncConnection,
    filter_: Literal["ALL", "OPEN", "ARCHIVED"] = "OPEN",
) -> list[Tournament]:
    # Same rule as `user_authenticated_or_public_dashboard`: open tournaments are visible to
    # everyone, archived ones only when their dashboard is public.
    query = f"""
        {TOURNAMENTS_WITH_PROGRESS}
        WHERE (tournaments.status = 'OPEN' OR tournaments.dashboard_public IS TRUE)
        """
    params: dict[str, Any] = {}

    if filter_ != "ALL":
        query += " AND tournaments.status = :status"
        params["status"] = filter_

    result = await conn.execute(text(query + TOURNAMENT_ORDER), params)
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


async def sql_move_tournament_start(
    conn: AsyncConnection, tournament_id: TournamentId, minutes: int
) -> None:
    query = """
        UPDATE tournaments
        SET start_time = start_time + make_interval(mins => :minutes)
        WHERE tournaments.id = :tournament_id
        """
    await conn.execute(text(query), {"tournament_id": tournament_id, "minutes": minutes})


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
