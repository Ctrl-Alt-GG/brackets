import pytest
from sqlalchemy.ext.asyncio import AsyncConnection

from bracket.sql.users import delete_user_and_owned_clubs
from bracket.utils.db_init import sql_create_dev_db


@pytest.mark.asyncio(loop_scope="session")
async def test_db_init(
    conn: AsyncConnection,
) -> None:
    user_id = await sql_create_dev_db(
        conn,
    )
    await delete_user_and_owned_clubs(conn, user_id)
