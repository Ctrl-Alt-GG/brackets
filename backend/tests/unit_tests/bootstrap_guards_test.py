import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from bracket.config import Environment
from bracket.utils import db_init


@pytest.mark.asyncio
async def test_development_seed_refuses_production_before_accessing_database(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(db_init, "environment", Environment.PRODUCTION)
    async with AsyncSession() as session:
        with pytest.raises(RuntimeError, match="requires ENVIRONMENT=DEVELOPMENT"):
            await db_init.sql_create_dev_db(session)
