from pydantic import BaseModel

from bracket.models.db.ranking import Ranking
from bracket.models.db.tournament import Tournament
from bracket.models.db.user import UserInDB


class AuthContext(BaseModel):
    """An organizer who owns a tournament, and the headers of their requests."""

    tournament: Tournament
    user: UserInDB
    headers: dict[str, str]
    ranking: Ranking
