from bracket.models.db.match import Match
from bracket.models.db.organizer import Organizer
from bracket.models.db.participation import (
    TournamentPlayer,
    TournamentTeam,
    TournamentTeamWithPlayers,
)
from bracket.models.db.player import Player
from bracket.models.db.ranking import Ranking
from bracket.models.db.shared import ApiModel
from bracket.models.db.stage_item_inputs import (
    StageItemInputOptionFinal,
    StageItemInputOptionTentative,
    StageItemInputUpdate,
)
from bracket.models.db.stage_tree import StageWithStageItems
from bracket.models.db.team import TeamWithMembers
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


class OrganizersResponse(DataResponse[list[Organizer]]):
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


class PlayersResponse(DataResponse[list[Player]]):
    pass


class SinglePlayerResponse(DataResponse[Player]):
    pass


class PaginatedTournamentPlayers(ApiModel):
    count: int
    players: list[TournamentPlayer]


class TournamentPlayersResponse(DataResponse[PaginatedTournamentPlayers]):
    pass


class StagesWithStageItemsResponse(DataResponse[list[StageWithStageItems]]):
    pass


class SingleMatchResponse(DataResponse[Match]):
    pass


class TeamsResponse(DataResponse[list[TeamWithMembers]]):
    pass


class SingleTeamResponse(DataResponse[TeamWithMembers]):
    pass


class PaginatedTournamentTeams(ApiModel):
    count: int
    teams: list[TournamentTeamWithPlayers]


class TournamentTeamsResponse(DataResponse[PaginatedTournamentTeams]):
    pass


class TournamentTeamResponse(DataResponse[TournamentTeam]):
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
