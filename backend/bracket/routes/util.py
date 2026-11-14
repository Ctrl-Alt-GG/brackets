from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.orm import joinedload
from starlette import status

from bracket import orm
from bracket.database import DbSession
from bracket.models.db.match import Match
from bracket.models.db.ranking import Ranking
from bracket.models.db.round import Round
from bracket.models.db.team import FullTeamWithPlayers, Team
from bracket.models.db.tournament import Tournament, TournamentStatus
from bracket.models.db.util import RoundWithMatches, StageItemWithRounds, StageWithStageItems
from bracket.sql.rounds import get_round_by_id
from bracket.sql.stage_items import get_stage_item
from bracket.sql.stages import get_full_tournament_details
from bracket.sql.teams import get_teams_with_members
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


async def round_dependency(
    tournament_id: TournamentId, round_id: RoundId, conn: DbSession
) -> Round:
    entity = await conn.scalar(
        select(orm.Round)
        .join(orm.StageItem)
        .join(orm.Stage)
        .where(orm.Round.id == round_id, orm.Stage.tournament_id == tournament_id)
        .execution_options(populate_existing=True)
    )
    round_ = Round.model_validate(entity) if entity is not None else None

    if round_ is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Could not find round with id {round_id}",
        )

    return round_


async def round_with_matches_dependency(
    tournament_id: TournamentId, round_id: RoundId, conn: DbSession
) -> RoundWithMatches:
    return await get_round_by_id(conn, tournament_id, round_id)


async def stage_dependency(
    tournament_id: TournamentId, stage_id: StageId, conn: DbSession
) -> StageWithStageItems:
    stages_result = await get_full_tournament_details(
        conn, tournament_id, no_draft_rounds=False, stage_id=stage_id
    )

    if len(stages_result) < 1:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Could not find stage with id {stage_id}",
        )

    return stages_result[0]


async def stage_item_dependency(
    tournament_id: TournamentId, stage_item_id: StageItemId, conn: DbSession
) -> StageItemWithRounds:
    return await get_stage_item(conn, tournament_id, stage_item_id=stage_item_id)


async def match_dependency(
    tournament_id: TournamentId, match_id: MatchId, conn: DbSession
) -> Match:
    entity = await conn.scalar(
        select(orm.Match)
        .join(orm.Round)
        .join(orm.StageItem)
        .join(orm.Stage)
        .where(orm.Match.id == match_id, orm.Stage.tournament_id == tournament_id)
        .options(
            joinedload(orm.Match.stage_item_input1).joinedload(orm.StageItemInput.team),
            joinedload(orm.Match.stage_item_input2).joinedload(orm.StageItemInput.team),
        )
        .execution_options(populate_existing=True)
    )
    match = Match.model_validate(entity) if entity is not None else None

    if match is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Could not find match with id {match_id}",
        )

    return match


async def team_dependency(tournament_id: TournamentId, team_id: TeamId, conn: DbSession) -> Team:
    entity = await conn.scalar(
        select(orm.Team)
        .where(orm.Team.id == team_id, orm.Team.tournament_id == tournament_id)
        .execution_options(populate_existing=True)
    )
    team = Team.model_validate(entity) if entity is not None else None

    if team is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Could not find team with id {team_id}",
        )

    return team


async def team_with_players_dependency(
    tournament_id: TournamentId, team_id: TeamId, conn: DbSession
) -> FullTeamWithPlayers:
    teams_with_members = await get_teams_with_members(conn, tournament_id, team_id=team_id)

    if len(teams_with_members) < 1:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Could not find team with id {team_id}",
        )

    return teams_with_members[0]


async def ranking_dependency(
    tournament_id: TournamentId, ranking_id: RankingId, conn: DbSession
) -> Ranking:
    entity = await conn.scalar(
        select(orm.Ranking)
        .where(orm.Ranking.id == ranking_id, orm.Ranking.tournament_id == tournament_id)
        .execution_options(populate_existing=True)
    )
    ranking = Ranking.model_validate(entity) if entity is not None else None

    if ranking is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Could not find ranking with id {ranking_id}",
        )

    return ranking


async def disallow_archived_tournament(tournament_id: TournamentId, conn: DbSession) -> Tournament:
    tournament = await sql_get_tournament(conn, tournament_id)
    if tournament.status is TournamentStatus.ARCHIVED:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Can't update archived tournament",
        )

    return tournament
