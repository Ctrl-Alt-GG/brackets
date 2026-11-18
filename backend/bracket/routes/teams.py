from typing import Annotated

from fastapi import APIRouter, BackgroundTasks, Depends, Query, UploadFile
from starlette.responses import FileResponse

from bracket.config import config
from bracket.database import DbSession
from bracket.logic import teams as team_logic
from bracket.logic.teams import get_team_with_totals, get_teams_with_totals
from bracket.models.db.team import FullTeamWithPlayers, Team, TeamBody, TeamMultiBody
from bracket.models.db.tournament import Tournament
from bracket.models.db.user import UserPublic
from bracket.routes.access import (
    user_authenticated_for_tournament,
    user_authenticated_or_public_dashboard,
    user_authenticated_or_rate_limited_visitor,
)
from bracket.routes.models import (
    PaginatedTeams,
    SingleTeamResponse,
    SuccessResponse,
    TeamsWithPlayersResponse,
)
from bracket.routes.resources import (
    disallow_archived_tournament,
    team_dependency,
    team_with_players_dependency,
)
from bracket.sql.teams import get_team_count, sql_delete_team, sql_update_team_logo
from bracket.utils.errors import ForeignKey, check_foreign_key_violation
from bracket.utils.id_types import TournamentId
from bracket.utils.pagination import ParticipantPagination
from bracket.utils.uploads import (
    UploadFolder,
    get_logo_response,
    remove_existing_upload,
    store_validated_image_upload,
)

router = APIRouter(prefix=config.api_prefix)

TournamentOrganizer = Annotated[UserPublic, Depends(user_authenticated_for_tournament)]
OpenTournament = Annotated[Tournament, Depends(disallow_archived_tournament)]
LoadedTeam = Annotated[Team, Depends(team_dependency)]


@router.get("/tournaments/{tournament_id}/teams", response_model=TeamsWithPlayersResponse)
async def get_teams(
    session: DbSession,
    tournament_id: TournamentId,
    pagination: Annotated[ParticipantPagination, Query()],
    _: Annotated[UserPublic | None, Depends(user_authenticated_or_rate_limited_visitor)],
) -> TeamsWithPlayersResponse:
    return TeamsWithPlayersResponse(
        data=PaginatedTeams(
            teams=await get_teams_with_totals(session, tournament_id, pagination=pagination),
            count=await get_team_count(session, tournament_id),
        )
    )


@router.put("/tournaments/{tournament_id}/teams/{team_id}", response_model=SingleTeamResponse)
async def update_team_by_id(
    session: DbSession,
    team_body: TeamBody,
    _: TournamentOrganizer,
    tournament: OpenTournament,
    team: LoadedTeam,
) -> SingleTeamResponse:
    return SingleTeamResponse(
        data=await team_logic.update_team(session, tournament, team.id, team_body)
    )


@router.post("/tournaments/{tournament_id}/teams/{team_id}/logo", response_model=SingleTeamResponse)
async def update_team_logo(
    session: DbSession,
    tournament_id: TournamentId,
    background_tasks: BackgroundTasks,
    _: TournamentOrganizer,
    __: OpenTournament,
    team: LoadedTeam,
    file: UploadFile | None = None,
) -> SingleTeamResponse:
    upload = (
        await store_validated_image_upload(file, UploadFolder.TEAM_LOGOS, session) if file else None
    )
    await sql_update_team_logo(session, team.id, upload.filename if upload else None)
    # Background tasks run after the response, so the new logo is committed by then. When the
    # transaction fails, there is no response and the previous logo stays.
    background_tasks.add_task(remove_existing_upload, UploadFolder.TEAM_LOGOS, team.logo_path)
    return SingleTeamResponse(data=await get_team_with_totals(session, tournament_id, team.id))


@router.get("/tournaments/{tournament_id}/teams/{team_id}/logo")
async def get_team_logo(
    _: Annotated[UserPublic | None, Depends(user_authenticated_or_public_dashboard)],
    team: LoadedTeam,
) -> FileResponse:
    return await get_logo_response(UploadFolder.TEAM_LOGOS, team.logo_path)


@router.delete("/tournaments/{tournament_id}/teams/{team_id}", response_model=SuccessResponse)
async def delete_team(
    session: DbSession,
    tournament_id: TournamentId,
    background_tasks: BackgroundTasks,
    _: TournamentOrganizer,
    __: OpenTournament,
    team: Annotated[FullTeamWithPlayers, Depends(team_with_players_dependency)],
) -> SuccessResponse:
    with check_foreign_key_violation(
        {
            ForeignKey.stage_item_inputs_team_id_fkey,
            ForeignKey.matches_stage_item_input1_id_fkey,
            ForeignKey.matches_stage_item_input2_id_fkey,
        }
    ):
        await sql_delete_team(session, tournament_id, team.id)

    # Background tasks run after the response, so the deletion is committed by then.
    background_tasks.add_task(remove_existing_upload, UploadFolder.TEAM_LOGOS, team.logo_path)
    return SuccessResponse()


@router.post("/tournaments/{tournament_id}/teams", response_model=SingleTeamResponse)
async def create_team(
    session: DbSession,
    team_to_insert: TeamBody,
    user: TournamentOrganizer,
    tournament: OpenTournament,
) -> SingleTeamResponse:
    return SingleTeamResponse(
        data=await team_logic.create_team(session, tournament, team_to_insert, user)
    )


@router.post("/tournaments/{tournament_id}/teams_multi", response_model=SuccessResponse)
async def create_multiple_teams(
    session: DbSession,
    team_body: TeamMultiBody,
    tournament_id: TournamentId,
    user: TournamentOrganizer,
    _: OpenTournament,
) -> SuccessResponse:
    await team_logic.create_teams_with_players(session, tournament_id, team_body, user)
    return SuccessResponse()
