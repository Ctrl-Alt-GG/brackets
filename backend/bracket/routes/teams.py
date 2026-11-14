from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, UploadFile
from sqlalchemy.ext.asyncio import AsyncSession
from starlette import status
from starlette.responses import FileResponse

from bracket.config import config
from bracket.database import DbSession
from bracket.logic.subscriptions import check_requirement
from bracket.logic.teams import get_team_logo_path
from bracket.models.db.player import PlayerBody
from bracket.models.db.team import (
    FullTeamWithPlayers,
    Team,
    TeamBody,
    TeamMultiBody,
)
from bracket.models.db.tournament import Tournament
from bracket.models.db.user import UserPublic
from bracket.routes.auth import (
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
from bracket.routes.util import (
    disallow_archived_tournament,
    team_dependency,
    team_with_players_dependency,
)
from bracket.sql.players import get_all_players_in_tournament, insert_player
from bracket.sql.teams import (
    get_team_by_id,
    get_team_count,
    get_teams_with_members,
    sql_add_team_player,
    sql_create_team,
    sql_delete_team,
    sql_set_team_members,
    sql_update_team,
    sql_update_team_logo,
)
from bracket.sql.validation import check_foreign_keys_belong_to_tournament
from bracket.utils.errors import ForeignKey, check_foreign_key_violation
from bracket.utils.id_types import PlayerId, TeamId, TournamentId
from bracket.utils.pagination import PaginationTeams
from bracket.utils.types import assert_some
from bracket.utils.uploads import (
    get_image_media_type,
    remove_existing_upload,
    store_validated_image_upload,
)

router = APIRouter(prefix=config.api_prefix)


async def check_players_are_free(
    conn: AsyncSession, team_id: TeamId, tournament: Tournament, player_ids: set[PlayerId]
) -> None:
    """Unless the tournament allows it, a player who joins a team isn't in another one."""
    if tournament.players_can_be_in_multiple_teams or len(player_ids) < 1:
        return

    for other_team in await get_teams_with_members(conn, tournament.id):
        if other_team.id == team_id:
            continue
        taken = next((player for player in other_team.players if player.id in player_ids), None)
        if taken is not None:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=(
                    f"{taken.name} is already in {other_team.name}. Players can be in one team, "
                    "unless the tournament's settings allow more."
                ),
            )


async def update_team_members(
    conn: AsyncSession, team_id: TeamId, tournament: Tournament, player_ids: set[PlayerId]
) -> None:
    [team] = await get_teams_with_members(conn, tournament.id, team_id=team_id)
    # Players who are already in the team stay in it. A tournament from before this rule, or one
    # that allowed several teams for a while, can have them in a second team, and its teams must
    # still be saveable.
    await check_players_are_free(conn, team_id, tournament, player_ids - set(team.player_ids))

    await sql_set_team_members(conn, team_id, player_ids, set(team.player_ids))


@router.get("/tournaments/{tournament_id}/teams", response_model=TeamsWithPlayersResponse)
async def get_teams(
    conn: DbSession,
    tournament_id: TournamentId,
    pagination: PaginationTeams = Depends(),
    _: UserPublic | None = Depends(user_authenticated_or_rate_limited_visitor),
) -> TeamsWithPlayersResponse:
    return TeamsWithPlayersResponse(
        data=PaginatedTeams(
            teams=await get_teams_with_members(conn, tournament_id, pagination=pagination),
            count=await get_team_count(conn, tournament_id),
        )
    )


@router.put("/tournaments/{tournament_id}/teams/{team_id}", response_model=SingleTeamResponse)
async def update_team_by_id(
    conn: DbSession,
    tournament_id: TournamentId,
    team_body: TeamBody,
    _: UserPublic = Depends(user_authenticated_for_tournament),
    tournament: Tournament = Depends(disallow_archived_tournament),
    team: Team = Depends(team_dependency),
) -> SingleTeamResponse:
    await check_foreign_keys_belong_to_tournament(conn, team_body, tournament_id)

    await sql_update_team(conn, tournament_id, team.id, team_body)
    await update_team_members(conn, team.id, tournament, team_body.player_ids)

    return SingleTeamResponse(
        data=assert_some(await get_team_by_id(conn, team.id, tournament_id, with_totals=True))
    )


@router.post("/tournaments/{tournament_id}/teams/{team_id}/logo", response_model=SingleTeamResponse)
async def update_team_logo(
    conn: DbSession,
    tournament_id: TournamentId,
    background_tasks: BackgroundTasks,
    file: UploadFile | None = None,
    _: UserPublic = Depends(user_authenticated_for_tournament),
    __: Tournament = Depends(disallow_archived_tournament),
    team: Team = Depends(team_dependency),
) -> SingleTeamResponse:
    filename = await store_validated_image_upload(file, "team-logos") if file else None
    await sql_update_team_logo(conn, team.id, filename)
    # Background tasks run after the response, so the new logo is committed by then.
    background_tasks.add_task(remove_existing_upload, "team-logos", team.logo_path)
    return SingleTeamResponse(
        data=assert_some(await get_team_by_id(conn, team.id, tournament_id, with_totals=True))
    )


@router.get("/tournaments/{tournament_id}/teams/{team_id}/logo")
async def get_team_logo(
    conn: DbSession,
    tournament_id: TournamentId,
    _: UserPublic | None = Depends(user_authenticated_or_public_dashboard),
    team: Team = Depends(team_dependency),
) -> FileResponse:
    logo_path = await get_team_logo_path(conn, tournament_id, team.id)
    if team.logo_path is None or logo_path is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Logo not found")

    return FileResponse(logo_path, media_type=get_image_media_type(team.logo_path))


@router.delete("/tournaments/{tournament_id}/teams/{team_id}", response_model=SuccessResponse)
async def delete_team(
    conn: DbSession,
    tournament_id: TournamentId,
    background_tasks: BackgroundTasks,
    _: UserPublic = Depends(user_authenticated_for_tournament),
    __: Tournament = Depends(disallow_archived_tournament),
    team: FullTeamWithPlayers = Depends(team_with_players_dependency),
) -> SuccessResponse:
    with check_foreign_key_violation(
        {
            ForeignKey.stage_item_inputs_team_id_fkey,
            ForeignKey.matches_stage_item_input1_id_fkey,
            ForeignKey.matches_stage_item_input2_id_fkey,
        }
    ):
        await sql_delete_team(conn, tournament_id, team.id)

    # Background tasks run after the response, so the deletion is committed by then.
    background_tasks.add_task(remove_existing_upload, "team-logos", team.logo_path)
    return SuccessResponse()


@router.post("/tournaments/{tournament_id}/teams", response_model=SingleTeamResponse)
async def create_team(
    conn: DbSession,
    team_to_insert: TeamBody,
    tournament_id: TournamentId,
    user: UserPublic = Depends(user_authenticated_for_tournament),
    tournament: Tournament = Depends(disallow_archived_tournament),
) -> SingleTeamResponse:
    await check_foreign_keys_belong_to_tournament(conn, team_to_insert, tournament_id)

    existing_teams = await get_teams_with_members(conn, tournament_id)
    check_requirement(existing_teams, user, "max_teams")

    last_record_id = await sql_create_team(
        conn, tournament_id, team_to_insert.name, team_to_insert.active
    )
    await update_team_members(conn, last_record_id, tournament, team_to_insert.player_ids)

    team_result = await get_team_by_id(conn, last_record_id, tournament_id, with_totals=True)
    assert team_result is not None
    return SingleTeamResponse(data=team_result)


@router.post("/tournaments/{tournament_id}/teams_multi", response_model=SuccessResponse)
async def create_multiple_teams(
    conn: DbSession,
    team_body: TeamMultiBody,
    tournament_id: TournamentId,
    user: UserPublic = Depends(user_authenticated_for_tournament),
    _: Tournament = Depends(disallow_archived_tournament),
) -> SuccessResponse:
    teams_with_players = team_body.teams_with_players
    player_count = sum(len(player_names) for _, player_names in teams_with_players)

    existing_teams = await get_teams_with_members(conn, tournament_id)
    existing_players = await get_all_players_in_tournament(conn, tournament_id)

    check_requirement(existing_teams, user, "max_teams", additions=len(teams_with_players))
    check_requirement(existing_players, user, "max_players", additions=player_count)

    for team_name, player_names in teams_with_players:
        team_id = await sql_create_team(conn, tournament_id, team_name, team_body.active)
        for player_name in player_names:
            player_id = await insert_player(
                conn, PlayerBody(name=player_name, active=team_body.active), tournament_id
            )
            await sql_add_team_player(conn, team_id, player_id)

    return SuccessResponse()
