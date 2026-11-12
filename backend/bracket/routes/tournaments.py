from typing import Literal

from async_lru import alru_cache
from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, UploadFile
from starlette import status
from starlette.responses import FileResponse, Response

from bracket.config import config
from bracket.database import DbConnection, engine
from bracket.logic.planning.matches import schedule_all_matches
from bracket.logic.subscriptions import check_requirement
from bracket.logic.tournaments import (
    get_tournament_details,
    get_tournament_logo_path,
    sql_delete_tournament_completely,
)
from bracket.models.db.ranking import RankingCreateBody
from bracket.models.db.tournament import (
    Tournament,
    TournamentBody,
    TournamentChangeStatusBody,
    TournamentUpdateBody,
)
from bracket.models.db.tournament_details import TournamentAccess
from bracket.models.db.user import UserPublic
from bracket.routes.auth import (
    user_authenticated,
    user_authenticated_for_tournament,
    user_authenticated_or_public_dashboard,
    user_authenticated_or_public_dashboard_by_endpoint_name,
)
from bracket.routes.models import (
    SuccessResponse,
    TournamentAccessResponse,
    TournamentDetailsResponse,
    TournamentResponse,
    TournamentsResponse,
)
from bracket.routes.util import disallow_archived_tournament
from bracket.schema import tournaments
from bracket.sql.rankings import (
    sql_create_ranking,
)
from bracket.sql.tournaments import (
    sql_create_tournament,
    sql_get_public_tournaments,
    sql_get_tournament,
    sql_get_tournament_by_endpoint_name,
    sql_get_tournaments,
    sql_update_tournament,
    sql_update_tournament_status,
)
from bracket.sql.users import get_user_access_to_club, get_which_clubs_has_user_access_to
from bracket.utils.errors import (
    UniqueIndex,
    check_unique_constraint_violation,
)
from bracket.utils.id_types import TournamentId
from bracket.utils.uploads import (
    get_image_media_type,
    remove_existing_upload,
    remove_existing_uploads,
    store_validated_image_upload,
)

router = APIRouter(prefix=config.api_prefix)

# How long the Details pages of a tournament are served from memory. Every visitor's page asks
# again twice a minute, so at an event hundreds of them ask for the same thing.
DETAILS_CACHE_SECONDS = 5


@alru_cache(maxsize=64, ttl=DETAILS_CACHE_SECONDS)
async def get_tournament_details_json(tournament_id: TournamentId) -> bytes:
    """
    The answer of the details endpoint, ready to send.

    Requests that arrive while it is being worked out wait for that one result, and it is kept
    for a few seconds, so the database does the work once however many visitors are watching.
    It has its own connection: the result outlives the request that happened to ask first.
    """
    async with engine.connect() as conn:
        details = await get_tournament_details(conn, tournament_id)
    return TournamentDetailsResponse(data=details).model_dump_json().encode()


@router.get("/tournaments/{tournament_id}/details", response_model=TournamentDetailsResponse)
async def get_tournament_details_by_id(
    tournament_id: TournamentId,
    _: UserPublic | None = Depends(user_authenticated_or_public_dashboard),
) -> Response:
    """
    Everything the Details pages of a tournament show, in one answer: the tournament, its stages
    without draft rounds, players, teams, rankings and standings.

    It can be a few seconds old.
    """
    return Response(
        content=await get_tournament_details_json(tournament_id), media_type="application/json"
    )


@router.get("/tournaments/{tournament_id}/access", response_model=TournamentAccessResponse)
async def get_tournament_access(
    tournament_id: TournamentId,
    user: UserPublic | None = Depends(user_authenticated_or_public_dashboard),
) -> TournamentAccessResponse:
    """Whether whoever asks can manage the tournament, or only follow it."""
    return TournamentAccessResponse(data=TournamentAccess(can_manage=user is not None))


@router.get("/tournaments/{tournament_id}", response_model=TournamentResponse)
async def get_tournament(
    conn: DbConnection,
    tournament_id: TournamentId,
    user: UserPublic | None = Depends(user_authenticated_or_public_dashboard),
) -> TournamentResponse:
    tournament = await sql_get_tournament(conn, tournament_id)
    return TournamentResponse(data=tournament)


@router.get("/tournaments", response_model=TournamentsResponse)
async def get_tournaments(
    conn: DbConnection,
    user: UserPublic | None = Depends(user_authenticated_or_public_dashboard_by_endpoint_name),
    filter_: Literal["ALL", "OPEN", "ARCHIVED"] = "OPEN",
    endpoint_name: str | None = None,
) -> TournamentsResponse:
    match user, endpoint_name:
        case None, None:
            return TournamentsResponse(data=await sql_get_public_tournaments(conn, filter_))

        case _, str() as endpoint_name:
            tournament = await sql_get_tournament_by_endpoint_name(conn, endpoint_name)
            if tournament is None:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail="Can't find this tournament",
                    headers={"WWW-Authenticate": "Bearer"},
                )
            return TournamentsResponse(data=[tournament])

        case _, _ if isinstance(user, UserPublic):
            user_club_ids = await get_which_clubs_has_user_access_to(conn, user.id)
            return TournamentsResponse(
                data=await sql_get_tournaments(conn, tuple(user_club_ids), endpoint_name, filter_)
            )

    raise RuntimeError()


@router.put("/tournaments/{tournament_id}", response_model=SuccessResponse)
async def update_tournament_by_id(
    conn: DbConnection,
    tournament_id: TournamentId,
    tournament_body: TournamentUpdateBody,
    _: UserPublic = Depends(user_authenticated_for_tournament),
    __: Tournament = Depends(disallow_archived_tournament),
) -> SuccessResponse:
    with check_unique_constraint_violation({UniqueIndex.ix_tournaments_dashboard_endpoint}):
        await sql_update_tournament(conn, tournament_id, tournament_body)

    await schedule_all_matches(conn, tournament_id)
    return SuccessResponse()


@router.delete("/tournaments/{tournament_id}", response_model=SuccessResponse)
async def delete_tournament(
    conn: DbConnection,
    tournament_id: TournamentId,
    background_tasks: BackgroundTasks,
    _: UserPublic = Depends(user_authenticated_for_tournament),
) -> SuccessResponse:
    uploads = await sql_delete_tournament_completely(conn, tournament_id)
    # Background tasks run after the response, so the deletion is committed by then.
    background_tasks.add_task(remove_existing_upload, "tournament-logos", uploads.tournament_logo)
    background_tasks.add_task(remove_existing_uploads, "team-logos", uploads.team_logos)
    return SuccessResponse()


@router.post("/tournaments/{tournament_id}/change-status", response_model=SuccessResponse)
async def change_status(
    conn: DbConnection,
    tournament_id: TournamentId,
    body: TournamentChangeStatusBody,
    _: UserPublic = Depends(user_authenticated_for_tournament),
) -> SuccessResponse:
    """
    Make a tournament archived or non-archived.
    """

    tournament = await sql_get_tournament(conn, tournament_id)
    if tournament.status == body.status:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Tournament already has the requested status",
            headers={"WWW-Authenticate": "Bearer"},
        )

    await sql_update_tournament_status(conn, tournament_id, body)
    return SuccessResponse()


@router.post("/tournaments", response_model=TournamentResponse)
async def create_tournament(
    conn: DbConnection,
    tournament_to_insert: TournamentBody,
    user: UserPublic = Depends(user_authenticated),
) -> TournamentResponse:
    if not await get_user_access_to_club(conn, tournament_to_insert.club_id, user.id):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Club ID is invalid")

    existing_tournaments = await sql_get_tournaments(conn, (tournament_to_insert.club_id,))
    check_requirement(existing_tournaments, user, "max_tournaments")

    with check_unique_constraint_violation({UniqueIndex.ix_tournaments_dashboard_endpoint}):
        tournament_id = await sql_create_tournament(conn, tournament_to_insert)

    ranking = RankingCreateBody()
    await sql_create_ranking(conn, tournament_id, ranking, position=0)

    return TournamentResponse(data=await sql_get_tournament(conn, tournament_id))


@router.post("/tournaments/{tournament_id}/logo")
async def upload_logo(
    conn: DbConnection,
    tournament_id: TournamentId,
    background_tasks: BackgroundTasks,
    file: UploadFile | None = None,
    _: UserPublic = Depends(user_authenticated_for_tournament),
    tournament: Tournament = Depends(disallow_archived_tournament),
) -> TournamentResponse:
    filename = await store_validated_image_upload(file, "tournament-logos") if file else None
    await conn.execute(
        tournaments.update().where(tournaments.c.id == tournament_id).values(logo_path=filename)
    )
    # Background tasks run after the response, so the new logo is committed by then.
    background_tasks.add_task(remove_existing_upload, "tournament-logos", tournament.logo_path)
    return TournamentResponse(data=await sql_get_tournament(conn, tournament_id))


@router.get("/tournaments/{tournament_id}/logo")
async def get_tournament_logo(
    conn: DbConnection,
    tournament_id: TournamentId,
    _: UserPublic | None = Depends(user_authenticated_or_public_dashboard),
) -> FileResponse:
    tournament = await sql_get_tournament(conn, tournament_id)
    logo_path = await get_tournament_logo_path(conn, tournament_id)
    if tournament.logo_path is None or logo_path is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Logo not found")

    return FileResponse(logo_path, media_type=get_image_media_type(tournament.logo_path))
