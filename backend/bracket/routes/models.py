from bracket.models.db.club import Club, ClubMember
from bracket.models.db.match import Match
from bracket.models.db.player import Player
from bracket.models.db.ranking import Ranking
from bracket.models.db.shared import ApiModel
from bracket.models.db.stage_item_inputs import (
    StageItemInputOptionFinal,
    StageItemInputOptionTentative,
    StageItemInputUpdate,
)
from bracket.models.db.stage_tree import StageWithStageItems
from bracket.models.db.team import FullTeamWithPlayers, Team
from bracket.models.db.tournament import Tournament, TournamentWithAccess
from bracket.models.db.tournament_details import (
    StageItemInputStanding,
    TournamentAccess,
    TournamentDetails,
    TournamentWorkspace,
)
from bracket.models.db.user import Token, UserPublic
from bracket.utils.id_types import StageId, StageItemId


class SuccessResponse(ApiModel):
    success: bool = True


class DataResponse[DataT](ApiModel):
    data: DataT


class ClubsResponse(DataResponse[list[Club]]):
    pass


class ClubResponse(DataResponse[Club | None]):
    pass


class ClubMembersResponse(DataResponse[list[ClubMember]]):
    pass


class TournamentResponse(DataResponse[Tournament]):
    pass


class TournamentsResponse(DataResponse[list[TournamentWithAccess]]):
    pass


class TournamentDetailsResponse(DataResponse[TournamentDetails]):
    pass


class TournamentWorkspaceResponse(DataResponse[TournamentWorkspace]):
    pass


class TournamentAccessResponse(DataResponse[TournamentAccess]):
    pass


class PaginatedPlayers(ApiModel):
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


class PaginatedTeams(ApiModel):
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


class AuthFeatureFlags(ApiModel):
    user_registration_enabled: bool


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
