"""The dependencies that load what a route's path names, or answer 404."""

from fastapi import HTTPException
from starlette import status

from bracket.database import DbSession
from bracket.models.db.match import Match
from bracket.models.db.ranking import Ranking
from bracket.models.db.round import Round
from bracket.models.db.stage_tree import RoundWithMatches, StageItemWithRounds, StageWithStageItems
from bracket.models.db.team import FullTeamWithPlayers, Team
from bracket.models.db.tournament import Tournament
from bracket.models.enums import TournamentStatus
from bracket.sql.matches import get_match_with_slots
from bracket.sql.rankings import get_ranking
from bracket.sql.rounds import get_round, get_round_by_id
from bracket.sql.stage_items import get_stage_item
from bracket.sql.stages import get_full_tournament_details
from bracket.sql.teams import get_team_by_id, get_teams_with_members
from bracket.sql.tournaments import sql_get_tournament
from bracket.utils.id_types import (
    MatchId,
    RankingId,
    RoundId,
    StageId,
    StageItemId,
    TeamId,
    TournamentId,
)


def not_found(kind: str, id_: int) -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_404_NOT_FOUND, detail=f"Could not find {kind} with id {id_}"
    )


async def round_dependency(
    tournament_id: TournamentId, round_id: RoundId, session: DbSession
) -> Round:
    round_ = await get_round(session, tournament_id, round_id)
    if round_ is None:
        raise not_found("round", round_id)
    return round_


async def round_with_matches_dependency(
    tournament_id: TournamentId, round_id: RoundId, session: DbSession
) -> RoundWithMatches:
    return await get_round_by_id(session, tournament_id, round_id)


async def stage_dependency(
    tournament_id: TournamentId, stage_id: StageId, session: DbSession
) -> StageWithStageItems:
    stages = await get_full_tournament_details(session, tournament_id, stage_id=stage_id)
    if len(stages) < 1:
        raise not_found("stage", stage_id)
    return stages[0]


async def stage_item_dependency(
    tournament_id: TournamentId, stage_item_id: StageItemId, session: DbSession
) -> StageItemWithRounds:
    return await get_stage_item(session, tournament_id, stage_item_id=stage_item_id)


async def match_dependency(
    tournament_id: TournamentId, match_id: MatchId, session: DbSession
) -> Match:
    match = await get_match_with_slots(session, tournament_id, match_id)
    if match is None:
        raise not_found("match", match_id)
    return match


async def team_dependency(tournament_id: TournamentId, team_id: TeamId, session: DbSession) -> Team:
    team = await get_team_by_id(session, team_id, tournament_id)
    if team is None:
        raise not_found("team", team_id)
    return team


async def team_with_players_dependency(
    tournament_id: TournamentId, team_id: TeamId, session: DbSession
) -> FullTeamWithPlayers:
    teams = await get_teams_with_members(session, tournament_id, team_id=team_id)
    if len(teams) < 1:
        raise not_found("team", team_id)
    return teams[0]


async def ranking_dependency(
    tournament_id: TournamentId, ranking_id: RankingId, session: DbSession
) -> Ranking:
    ranking = await get_ranking(session, tournament_id, ranking_id)
    if ranking is None:
        raise not_found("ranking", ranking_id)
    return ranking


async def disallow_archived_tournament(
    tournament_id: TournamentId, session: DbSession
) -> Tournament:
    tournament = await sql_get_tournament(session, tournament_id)
    if tournament.status is TournamentStatus.ARCHIVED:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Can't update archived tournament",
        )

    return tournament
