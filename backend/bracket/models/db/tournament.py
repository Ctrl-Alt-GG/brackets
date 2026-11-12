from enum import auto

from heliclockter import datetime_utc
from pydantic import Field

from bracket.models.db.match import MAX_MINUTES
from bracket.models.db.shared import BaseModelORM
from bracket.utils.id_types import ClubId, TournamentId
from bracket.utils.pydantic import DashboardEndpoint, Name
from bracket.utils.types import EnumAutoStr


class TournamentStatus(EnumAutoStr):
    OPEN = auto()
    ARCHIVED = auto()


class TournamentInsertable(BaseModelORM):
    club_id: ClubId
    name: str
    created: datetime_utc
    start_time: datetime_utc
    duration_minutes: int = Field(..., ge=1)
    margin_minutes: int = Field(..., ge=0)
    dashboard_public: bool
    dashboard_endpoint: str | None = None
    logo_path: str | None = None
    players_can_be_in_multiple_teams: bool
    status: TournamentStatus = TournamentStatus.OPEN


class Tournament(TournamentInsertable):
    id: TournamentId
    # How far the published matches have got. A tournament whose matches all have a result is
    # over, also while its organizer hasn't archived it yet.
    matches_total: int = 0
    matches_played: int = 0
    last_match_end: datetime_utc | None = None


class TournamentUpdateBody(BaseModelORM):
    start_time: datetime_utc
    name: Name
    dashboard_public: bool
    dashboard_endpoint: DashboardEndpoint = None
    players_can_be_in_multiple_teams: bool
    duration_minutes: int = Field(..., ge=1, le=MAX_MINUTES)
    margin_minutes: int = Field(..., ge=0, le=MAX_MINUTES)


class TournamentChangeStatusBody(BaseModelORM):
    status: TournamentStatus


class TournamentBody(TournamentUpdateBody):
    club_id: ClubId
