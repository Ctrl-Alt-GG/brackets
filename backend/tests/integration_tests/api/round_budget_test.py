from http import HTTPMethod

import pytest
from sqlalchemy import func, select

from bracket import orm
from bracket.database import session_scope
from bracket.logic.subscriptions import LIMITS, Limit
from bracket.models.enums import UserAccountType
from tests.integration_tests.api.flows import api_tournament
from tests.integration_tests.models import AuthContext

REFUSED = {"detail": "That would be more than the 8 rounds in a tournament that are allowed."}


async def count(entity: type[orm.Round] | type[orm.StageItem] | type[orm.Match], id_: int) -> int:
    async with session_scope(read_only=True) as session:
        return int(
            await session.scalar(
                select(func.count()).select_from(entity).where(entity.tournament_id == id_)
            )
            or 0
        )


@pytest.mark.asyncio(loop_scope="session")
async def test_generated_rounds_count_towards_the_limit(
    startup_and_shutdown_uvicorn_server: None,
    auth_context: AuthContext,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setitem(LIMITS[UserAccountType.REGULAR], Limit.ROUNDS, 8)
    async with api_tournament(auth_context) as flow:
        stage = await flow.add_stage()
        # Five teams play five rounds, four teams three: the limit exactly.
        await flow.add_stage_item(stage, "ROUND_ROBIN", 5, "Odd group")
        await flow.add_stage_item(stage, "ROUND_ROBIN", 4, "Even group")
        assert await count(orm.Round, flow.id) == 8
        stage_items, matches = await count(orm.StageItem, flow.id), await count(orm.Match, flow.id)

        knockout = await flow.call(
            HTTPMethod.POST,
            "stage_items",
            {"stage_id": stage, "type": "SINGLE_ELIMINATION", "team_count": 2},
        )
        assert knockout == REFUSED
        # Nothing of the refused stage item stays.
        assert await count(orm.StageItem, flow.id) == stage_items
        assert await count(orm.Round, flow.id) == 8
        assert await count(orm.Match, flow.id) == matches

        # A Swiss stage item starts without rounds, but drawing one would exceed the limit.
        swiss = await flow.add_stage_item(stage, "SWISS", 2, "Swiss")
        assert await flow.call(HTTPMethod.POST, "rounds", {"stage_item_id": swiss}) == REFUSED
        assert await count(orm.Round, flow.id) == 8
