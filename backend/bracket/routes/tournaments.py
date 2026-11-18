from typing import Annotated

from async_lru import alru_cache
from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, UploadFile
from starlette import status
from starlette.responses import FileResponse, Response

from bracket.config import config
from bracket.database import DbSession, session_scope
from bracket.logic import tournaments as tournament_logic
from bracket.logic.tournaments import delete_tournament_completely, get_tournament_details
from bracket.models.db.tournament import (
    Tournament,
    TournamentBody,
    TournamentChangeStatusBody,
    TournamentUpdateBody,
    TournamentWithAccess,
)
from bracket.models.db.tournament_details import TournamentAccess
from bracket.models.db.user import UserPublic
from bracket.routes.access import (
    AuthenticatedUser,
    user_authenticated_for_cached_dashboard,
    user_authenticated_for_tournament,
    user_authenticated_or_public_dashboard,
    user_authenticated_or_visitor,
)
from bracket.routes.models import (
    SuccessResponse,
    TournamentAccessResponse,
    TournamentDetailsResponse,
    TournamentResponse,
    TournamentsResponse,
    TournamentWorkspaceResponse,
)
from bracket.routes.resources import disallow_archived_tournament
from bracket.sql.tournaments import (
    TournamentFilter,
    sql_get_tournament,
    sql_get_tournament_by_endpoint_name,
    sql_get_visible_tournaments,
    sql_update_tournament_logo,
    sql_update_tournament_status,
)
from bracket.sql.users import get_which_clubs_has_user_access_to
from bracket.utils.id_types import TournamentId
from bracket.utils.uploads import (
    UploadFolder,
    get_logo_response,
    remove_existing_upload,
    remove_existing_uploads,
    store_validated_image_upload,
)

router = APIRouter(prefix=config.api_prefix)

TournamentOrganizer = Annotated[UserPublic, Depends(user_authenticated_for_tournament)]
OrganizerOrVisitor = Annotated[UserPublic | None, Depends(user_authenticated_or_public_dashboard)]

# How long the Details pages of a tournament are served from memory. Every visitor's page asks
# again twice a minute, so at an event hundreds of them ask for the same thing.
DETAILS_CACHE_SECONDS = 5


@alru_cache(maxsize=64, ttl=DETAILS_CACHE_SECONDS)
async def get_tournament_details_json(tournament_id: TournamentId) -> bytes:
    """
    The answer of the details endpoint, ready to send.

    Requests that arrive while it is being worked out wait for that one result, and it is kept
    for a few seconds, so the database does the work once however many visitors are watching.
    It has its own session: the result outlives the request that happened to ask first.
    """
    async with session_scope(read_only=True) as session:
        details = await get_tournament_details(session, tournament_id)
    return TournamentDetailsResponse(data=details).model_dump_json().encode()


@router.get("/tournaments/{tournament_id}/details", response_model=TournamentDetailsResponse)
async def get_tournament_details_by_id(
    tournament_id: TournamentId,
    _: Annotated[UserPublic | None, Depends(user_authenticated_for_cached_dashboard)],
) -> Response:
    """
    Everything the Details pages of a tournament show, in one answer: the tournament, its stages
    without draft rounds, players, teams, rankings and standings.

    It can be a few seconds old.
    """
    return Response(
        content=await get_tournament_details_json(tournament_id), media_type="application/json"
    )


@router.get("/tournaments/{tournament_id}/workspace", response_model=TournamentWorkspaceResponse)
async def get_tournament_workspace(
    session: DbSession, tournament_id: TournamentId, _: TournamentOrganizer
) -> TournamentWorkspaceResponse:
    """
    Everything the organizers' pages of a tournament show, in one answer from one snapshot: the
    stages with their draft rounds, players, teams, rankings, standings, what the stages' slots
    can take and who would advance into the next stage.
    """
    return TournamentWorkspaceResponse(
        data=await tournament_logic.get_tournament_workspace(session, tournament_id)
    )


@router.get("/tournaments/{tournament_id}/access", response_model=TournamentAccessResponse)
async def get_tournament_access(user: OrganizerOrVisitor) -> TournamentAccessResponse:
    """Whether whoever asks can manage the tournament, or only follow it."""
    return TournamentAccessResponse(data=TournamentAccess(can_manage=user is not None))


@router.get("/tournaments/{tournament_id}", response_model=TournamentResponse)
async def get_tournament(
    session: DbSession, tournament_id: TournamentId, _: OrganizerOrVisitor
) -> TournamentResponse:
    return TournamentResponse(data=await sql_get_tournament(session, tournament_id))


@router.get("/tournaments", response_model=TournamentsResponse)
async def get_tournaments(
    session: DbSession,
    user: Annotated[UserPublic | None, Depends(user_authenticated_or_visitor)],
    filter_: TournamentFilter = "OPEN",
    endpoint_name: str | None = None,
) -> TournamentsResponse:
    """
    The tournaments that everyone may see, and for an organizer also those of their events, with
    whether the one who asks can manage each.

    With `endpoint_name`, only the tournament whose Details link that is.
    """
    managed_club_ids = (
        await get_which_clubs_has_user_access_to(session, user.id) if user is not None else set()
    )
    if endpoint_name is not None:
        tournament = await sql_get_tournament_by_endpoint_name(session, endpoint_name)
        if tournament is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f'No tournament has the Details link "{endpoint_name}"',
            )
        tournaments_ = [tournament]
    else:
        tournaments_ = await sql_get_visible_tournaments(session, managed_club_ids, filter_)

    return TournamentsResponse(
        data=[
            TournamentWithAccess(
                **tournament.model_dump(), can_manage=tournament.club_id in managed_club_ids
            )
            for tournament in tournaments_
        ]
    )


@router.put("/tournaments/{tournament_id}", response_model=SuccessResponse)
async def update_tournament_by_id(
    session: DbSession,
    tournament_id: TournamentId,
    tournament_body: TournamentUpdateBody,
    _: TournamentOrganizer,
    __: Annotated[Tournament, Depends(disallow_archived_tournament)],
) -> SuccessResponse:
    await tournament_logic.update_tournament(session, tournament_id, tournament_body)
    return SuccessResponse()


@router.delete("/tournaments/{tournament_id}", response_model=SuccessResponse)
async def delete_tournament(
    session: DbSession,
    tournament_id: TournamentId,
    background_tasks: BackgroundTasks,
    _: TournamentOrganizer,
) -> SuccessResponse:
    uploads = await delete_tournament_completely(session, tournament_id)
    # Background tasks run after the response, so the deletion is committed by then.
    background_tasks.add_task(
        remove_existing_upload, UploadFolder.TOURNAMENT_LOGOS, uploads.tournament_logo
    )
    background_tasks.add_task(remove_existing_uploads, UploadFolder.TEAM_LOGOS, uploads.team_logos)
    return SuccessResponse()


@router.post("/tournaments/{tournament_id}/change-status", response_model=SuccessResponse)
async def change_status(
    session: DbSession,
    tournament_id: TournamentId,
    body: TournamentChangeStatusBody,
    _: TournamentOrganizer,
) -> SuccessResponse:
    """
    Make a tournament archived or non-archived.
    """
    tournament = await sql_get_tournament(session, tournament_id)
    if tournament.status == body.status:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Tournament already has the requested status",
        )

    await sql_update_tournament_status(session, tournament_id, body)
    return SuccessResponse()


@router.post("/tournaments", response_model=TournamentResponse)
async def create_tournament(
    session: DbSession, tournament_to_insert: TournamentBody, user: AuthenticatedUser
) -> TournamentResponse:
    return TournamentResponse(
        data=await tournament_logic.create_tournament(session, tournament_to_insert, user)
    )


@router.post("/tournaments/{tournament_id}/logo")
async def upload_logo(
    session: DbSession,
    tournament_id: TournamentId,
    background_tasks: BackgroundTasks,
    _: TournamentOrganizer,
    tournament: Annotated[Tournament, Depends(disallow_archived_tournament)],
    file: UploadFile | None = None,
) -> TournamentResponse:
    upload = (
        await store_validated_image_upload(file, UploadFolder.TOURNAMENT_LOGOS, session)
        if file
        else None
    )
    await sql_update_tournament_logo(session, tournament_id, upload.filename if upload else None)
    # Background tasks run after the response, so the new logo is committed by then. When the
    # transaction fails, there is no response and the previous logo stays.
    background_tasks.add_task(
        remove_existing_upload, UploadFolder.TOURNAMENT_LOGOS, tournament.logo_path
    )
    return TournamentResponse(data=await sql_get_tournament(session, tournament_id))


@router.get("/tournaments/{tournament_id}/logo")
async def get_tournament_logo(
    session: DbSession, tournament_id: TournamentId, _: OrganizerOrVisitor
) -> FileResponse:
    tournament = await sql_get_tournament(session, tournament_id)
    return await get_logo_response(UploadFolder.TOURNAMENT_LOGOS, tournament.logo_path)
