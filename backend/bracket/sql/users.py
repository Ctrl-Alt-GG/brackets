from sqlalchemy import func, text
from sqlalchemy.ext.asyncio import AsyncConnection

from bracket.logic.tournaments import sql_delete_tournament_completely
from bracket.models.db.account import UserAccountType
from bracket.models.db.user import User, UserInDB, UserInsertable, UserPublic, UserToUpdate
from bracket.schema import users
from bracket.sql.clubs import get_clubs_for_user_id, sql_delete_club
from bracket.sql.tournaments import sql_get_tournaments
from bracket.utils.db import fetch_one_parsed
from bracket.utils.id_types import ClubId, TournamentId, UserId
from bracket.utils.security import normalize_email


async def get_user_access_to_tournament(
    conn: AsyncConnection, tournament_id: TournamentId, user_id: UserId
) -> bool:
    query = """
        SELECT EXISTS (
            SELECT 1
            FROM users_x_clubs
            JOIN tournaments ON tournaments.club_id = users_x_clubs.club_id
            WHERE users_x_clubs.user_id = :user_id
            AND tournaments.id = :tournament_id
        )
        """
    return bool(
        await conn.scalar(text(query), {"user_id": user_id, "tournament_id": tournament_id})
    )


async def get_which_clubs_has_user_access_to(conn: AsyncConnection, user_id: UserId) -> set[ClubId]:
    query = """
        SELECT club_id
        FROM users_x_clubs
        WHERE user_id = :user_id
        """
    result = await conn.execute(text(query), {"user_id": user_id})
    return {club.club_id for club in result}


async def get_user_access_to_club(conn: AsyncConnection, club_id: ClubId, user_id: UserId) -> bool:
    query = """
        SELECT EXISTS (
            SELECT 1
            FROM users_x_clubs
            WHERE user_id = :user_id
            AND club_id = :club_id
        )
        """
    return bool(await conn.scalar(text(query), {"user_id": user_id, "club_id": club_id}))


async def update_user(conn: AsyncConnection, user_id: UserId, user: UserToUpdate) -> None:
    query = """
        UPDATE users
        SET name = :name, email = :email
        WHERE id = :user_id
        """
    await conn.execute(
        text(query),
        {"user_id": user_id, "name": user.name, "email": normalize_email(user.email)},
    )


async def update_user_account_type(
    conn: AsyncConnection, user_id: UserId, account_type: UserAccountType
) -> None:
    query = """
        UPDATE users
        SET account_type = :account_type
        WHERE id = :user_id
        """
    await conn.execute(text(query), {"user_id": user_id, "account_type": account_type.value})


async def update_user_password(conn: AsyncConnection, user_id: UserId, password_hash: str) -> None:
    query = """
        UPDATE users
        SET password_hash = :password_hash
        WHERE id = :user_id
        """
    await conn.execute(text(query), {"user_id": user_id, "password_hash": password_hash})


async def get_user_by_id(conn: AsyncConnection, user_id: UserId) -> UserPublic | None:
    query = """
        SELECT *
        FROM users
        WHERE id = :user_id
        """
    result = (await conn.execute(text(query), {"user_id": user_id})).first()
    return UserPublic.model_validate(result._mapping) if result is not None else None


async def create_user(conn: AsyncConnection, user: UserInsertable) -> User:
    query = """
        INSERT INTO users (email, name, password_hash, created, account_type)
        VALUES (:email, :name, :password_hash, :created, :account_type)
        RETURNING *
        """
    result = await conn.execute(
        text(query),
        {
            "password_hash": user.password_hash,
            "name": user.name,
            "email": normalize_email(user.email),
            "created": user.created,
            "account_type": user.account_type.value,
        },
    )
    return User.model_validate(result.one()._mapping)


async def delete_user(conn: AsyncConnection, user_id: UserId) -> None:
    query = """
        DELETE FROM users
        WHERE id = :user_id
        """
    await conn.execute(text(query), {"user_id": user_id})


async def check_whether_email_is_in_use(conn: AsyncConnection, email: str) -> bool:
    query = """
        SELECT id
        FROM users
        WHERE LOWER(email) = LOWER(:email)
        """
    result = await conn.execute(text(query), {"email": normalize_email(email)})
    return result.first() is not None


async def get_user(conn: AsyncConnection, email: str) -> UserInDB | None:
    # An exact match on the unique `ix_users_email_lower` index. Never a pattern match such as
    # `ILIKE`: `%` and `_` are valid in emails, so `%@example.org` would match other accounts.
    return await fetch_one_parsed(
        conn,
        UserInDB,
        users.select().where(func.lower(users.c.email) == normalize_email(email)),
    )


async def get_user_in_db(conn: AsyncConnection, user_id: UserId) -> UserInDB | None:
    return await fetch_one_parsed(conn, UserInDB, users.select().where(users.c.id == user_id))


async def delete_user_and_owned_clubs(conn: AsyncConnection, user_id: UserId) -> list[str]:
    """
    Delete the user with their clubs and tournaments.

    Returns the logos of the deleted tournaments, which the caller discards once the deletion is
    committed.
    """
    logos = []
    for club in await get_clubs_for_user_id(conn, user_id):
        for tournament in await sql_get_tournaments(conn, (club.id,), None):
            if (logo := await sql_delete_tournament_completely(conn, tournament.id)) is not None:
                logos.append(logo)

        await sql_delete_club(conn, club.id)

    await delete_user(conn, user_id)
    return logos
