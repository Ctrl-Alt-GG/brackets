import os
import subprocess
import sys

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from bracket import development_seed
from bracket.config import Environment


@pytest.mark.asyncio
async def test_development_seed_refuses_production_before_accessing_database(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(development_seed, "environment", Environment.PRODUCTION)
    async with AsyncSession() as session:
        with pytest.raises(RuntimeError, match="requires ENVIRONMENT=DEVELOPMENT"):
            await development_seed.create_dev_db(session)


def test_production_startup_leaves_development_seeding_out() -> None:
    """The application and the CLI load the example data only for `create-dev-db`."""
    imported = subprocess.run(
        [
            sys.executable,
            "-c",
            "import sys, bracket.app, cli; print(' '.join(sorted(sys.modules)))",
        ],
        env=os.environ,
        capture_output=True,
        text=True,
        check=True,
    ).stdout.split()
    assert "bracket.development_seed" not in imported
    assert not [module for module in imported if module.startswith("tests")]
