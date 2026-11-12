from pydantic import BaseModel

from bracket.logic.scheduling.handle_stage_activation import StageItemInputUpdate
from bracket.models.db.club import Club, ClubMember
from bracket.models.db.match import Match
from bracket.models.db.player import Player
from bracket.models.db.ranking import Ranking
from bracket.models.db.stage_item_inputs import (
    StageItemInputOptionFinal,
    StageItemInputOptionTentative,
)
from bracket.models.db.team import FullTeamWithPlayers, Team
from bracket.models.db.tournament import Tournament
from bracket.models.db.tournament_details import (
    StageItemInputStanding,
    TournamentAccess,
    TournamentDetails,
)
from bracket.models.db.user import UserPublic
from bracket.models.db.util import StageWithStageItems
from bracket.routes.auth import Token
from bracket.utils.id_types import StageId, StageItemId


class SuccessResponse(BaseModel):
    success: bool = True


class DataResponse[DataT](BaseModel):
    data: DataT


class ClubsResponse(DataResponse[list[Club]]):
    pass


class ClubResponse(DataResponse[Club | None]):
    pass


class ClubMembersResponse(DataResponse[list[ClubMember]]):
    pass


class TournamentResponse(DataResponse[Tournament]):
    pass


class TournamentsResponse(DataResponse[list[Tournament]]):
    pass


class TournamentDetailsResponse(DataResponse[TournamentDetails]):
    pass


class TournamentAccessResponse(DataResponse[TournamentAccess]):
    pass


class PaginatedPlayers(BaseModel):
    count: int
    players: list[Player]


class PlayersResponse(DataResponse[PaginatedPlayers]):
    pass


class SinglePlayerResponse(DataResponse[Player]):
    pass


class StagesWithStageItemsResponse(DataResponse[list[StageWithStageItems]]):
    pass


class SingleMatchResponse(DataResponse[Match]):
    pass


class PaginatedTeams(BaseModel):
    count: int
    teams: list[FullTeamWithPlayers]


class TeamsWithPlayersResponse(DataResponse[PaginatedTeams]):
    pass


class SingleTeamResponse(DataResponse[Team]):
    pass


class UserPublicResponse(DataResponse[UserPublic]):
    pass


class TokenResponse(DataResponse[Token]):
    pass


class AuthFeatureFlags(BaseModel):
    user_registration_enabled: bool
    password_reset_enabled: bool = False


class AuthFeatureFlagsResponse(DataResponse[AuthFeatureFlags]):
    pass


class RankingsResponse(DataResponse[list[Ranking]]):
    pass


class StandingsResponse(DataResponse[dict[StageItemId, list[StageItemInputStanding]]]):
    pass


class StageItemInputOptionsResponse(
    DataResponse[dict[StageId, list[StageItemInputOptionTentative | StageItemInputOptionFinal]]]
):
    pass


class StageRankingResponse(DataResponse[dict[StageItemId, list[StageItemInputUpdate]]]):
    pass
