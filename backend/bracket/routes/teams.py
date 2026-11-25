"""
Teams, which every organizer shares. The teams of one tournament are in
`bracket.routes.participation`.
"""

from typing import Annotated

from fastapi import APIRouter, BackgroundTasks, Depends, UploadFile
from starlette.responses import FileResponse

from bracket.config import config
from bracket.database import DbSession
from bracket.logic import teams as team_logic
from bracket.models.db.team import Team, TeamBody
from bracket.routes.access import AuthenticatedUser
from bracket.routes.models import SingleTeamResponse, SuccessResponse, TeamsResponse
from bracket.routes.resources import team_dependency
from bracket.sql.teams import get_teams_with_members, sql_update_team_logo
from bracket.utils.id_types import TeamId
from bracket.utils.uploads import (
    UploadFolder,
    get_logo_response,
    remove_existing_upload,
    store_validated_image_upload,
)

router = APIRouter(prefix=config.api_prefix)

LoadedTeam = Annotated[Team, Depends(team_dependency)]


@router.get("/teams", response_model=TeamsResponse)
async def get_teams(session: DbSession, _: AuthenticatedUser) -> TeamsResponse:
    """Every team by name, with its roster and the tournaments it takes part in."""
    return TeamsResponse(data=await get_teams_with_members(session))


@router.post("/teams", response_model=SingleTeamResponse)
async def create_team(
    session: DbSession, body: TeamBody, user: AuthenticatedUser
) -> SingleTeamResponse:
    return SingleTeamResponse(data=await team_logic.create_team(session, body, user))


@router.put("/teams/{team_id}", response_model=SingleTeamResponse)
async def update_team(
    session: DbSession, team_id: TeamId, body: TeamBody, user: AuthenticatedUser
) -> SingleTeamResponse:
    """
    Rename the team and replace its roster. The lineups of its open tournaments follow the roster,
    and their schedules make room for what the new players play elsewhere.
    """
    return SingleTeamResponse(data=await team_logic.update_team(session, team_id, body, user))


@router.delete("/teams/{team_id}", response_model=SuccessResponse)
async def delete_team(
    session: DbSession, background_tasks: BackgroundTasks, _: AuthenticatedUser, team: LoadedTeam
) -> SuccessResponse:
    """Delete a team that takes part in no tournament."""
    await team_logic.delete_team(session, team.id)
    # Background tasks run after the response, so the deletion is committed by then.
    background_tasks.add_task(remove_existing_upload, UploadFolder.TEAM_LOGOS, team.logo_path)
    return SuccessResponse()


@router.post("/teams/{team_id}/logo", response_model=SingleTeamResponse)
async def update_team_logo(
    session: DbSession,
    background_tasks: BackgroundTasks,
    _: AuthenticatedUser,
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
    return SingleTeamResponse(data=await team_logic.get_team_with_members(session, team.id))


@router.get("/teams/{team_id}/logo")
async def get_team_logo(team: LoadedTeam) -> FileResponse:
    """Anyone can see a team's logo: the Details pages of its tournaments show it."""
    return await get_logo_response(UploadFolder.TEAM_LOGOS, team.logo_path)
