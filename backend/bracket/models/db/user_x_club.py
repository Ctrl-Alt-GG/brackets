from bracket.models.db.shared import BaseModelORM
from bracket.models.enums import UserXClubRelation
from bracket.utils.id_types import ClubId, UserId, UserXClubId


class UserXClubInsertable(BaseModelORM):
    user_id: UserId
    club_id: ClubId
    relation: UserXClubRelation


class UserXClub(UserXClubInsertable):
    id: UserXClubId
