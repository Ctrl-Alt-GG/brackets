from bracket.sql.teams import get_team_by_id
from bracket.utils.id_types import TeamId, TournamentId
from bracket.utils.uploads import get_existing_upload_path


async def get_team_logo_path(tournament_id: TournamentId, team_id: TeamId) -> str | None:
    team = await get_team_by_id(team_id, tournament_id)
    logo_path = await get_existing_upload_path(
        "team-logos", team.logo_path if team is not None else None
    )
    return str(logo_path) if logo_path is not None else None
