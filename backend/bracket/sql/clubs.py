from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncConnection

from bracket.models.db.club import Club, ClubCreateBody, ClubMember, ClubUpdateBody
from bracket.models.db.user_x_club import UserXClubRelation
from bracket.utils.id_types import ClubId, UserId
from bracket.utils.types import assert_some


async def sql_give_user_access_to_club(
    conn: AsyncConnection,
    user_id: UserId,
    club_id: ClubId,
    relation: UserXClubRelation = UserXClubRelation.OWNER,
) -> None:
    query_many_to_many = """
        INSERT INTO users_x_clubs (club_id, user_id, relation)
        VALUES (:club_id, :user_id, CAST(:relation AS user_x_club_relation))
        """
    await conn.execute(
        text(query_many_to_many),
        {"club_id": assert_some(club_id), "user_id": user_id, "relation": relation.value},
    )


async def sql_remove_user_from_club(
    conn: AsyncConnection, user_id: UserId, club_id: ClubId
) -> None:
    query = "DELETE FROM users_x_clubs WHERE club_id = :club_id AND user_id = :user_id"
    await conn.execute(text(query), {"club_id": club_id, "user_id": user_id})


async def get_club_members(conn: AsyncConnection, club_id: ClubId) -> list[ClubMember]:
    query = """
        SELECT users.id AS user_id, users.name, users.email, uxc.relation
        FROM users_x_clubs uxc
        JOIN users ON users.id = uxc.user_id
        WHERE uxc.club_id = :club_id
        ORDER BY uxc.relation = 'OWNER' DESC, users.name, users.id
        """
    results = await conn.execute(text(query), {"club_id": club_id})
    return [ClubMember.model_validate(result._mapping) for result in results]


async def create_club(conn: AsyncConnection, club: ClubCreateBody, user_id: UserId) -> Club:
    query = """
        INSERT INTO clubs (name, created)
        VALUES (:name, NOW())
        RETURNING *
    """
    result = (await conn.execute(text(query), {"name": club.name})).first()
    if result is None:
        raise ValueError("Could not create club")

    club_created = Club.model_validate(result._mapping)
    await sql_give_user_access_to_club(conn, user_id, club_created.id)
    return club_created


async def sql_update_club(
    conn: AsyncConnection, club_id: ClubId, club: ClubUpdateBody
) -> Club | None:
    query = """
        UPDATE clubs
        SET name = :name
        WHERE id = :club_id
        RETURNING *
        """
    result = (await conn.execute(text(query), {"name": club.name, "club_id": club_id})).first()
    return Club.model_validate(result._mapping) if result is not None else None


async def sql_delete_club(conn: AsyncConnection, club_id: ClubId) -> None:
    query = """
        DELETE FROM clubs
        WHERE id = :club_id
        """
    await conn.execute(text(query), {"club_id": club_id})


async def get_clubs_for_user_id(conn: AsyncConnection, user_id: UserId) -> list[Club]:
    query = """
        SELECT clubs.* FROM clubs
        JOIN users_x_clubs uxc on clubs.id = uxc.club_id
        WHERE uxc.user_id = :user_id
        """
    results = await conn.execute(text(query), {"user_id": user_id})
    return [Club.model_validate(result._mapping) for result in results]
