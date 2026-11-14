from decimal import Decimal
from http import HTTPMethod
from unittest.mock import ANY

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from bracket import orm
from bracket.models.db.ranking import Ranking
from bracket.sql.rankings import (
    get_all_rankings_in_tournament,
    sql_delete_ranking,
)
from bracket.utils.dummy_records import DUMMY_RANKING1, DUMMY_TEAM1, DUMMY_TOURNAMENT
from tests.integration_tests.api.shared import SUCCESS_RESPONSE, send_tournament_request
from tests.integration_tests.models import AuthContext
from tests.integration_tests.sql import inserted_ranking, inserted_team, inserted_tournament


@pytest.mark.asyncio(loop_scope="session")
async def test_rankings_endpoint(
    startup_and_shutdown_uvicorn_server: None, auth_context: AuthContext
) -> None:
    async with inserted_team(
        DUMMY_TEAM1.model_copy(update={"tournament_id": auth_context.tournament.id})
    ):
        assert await send_tournament_request(HTTPMethod.GET, "rankings", auth_context, {}) == {
            "data": [
                {
                    "created": ANY,
                    "id": auth_context.ranking.id,
                    "position": 0,
                    "win_points": "1.0",
                    "draw_points": "0.5",
                    "loss_points": "0.0",
                    "add_score_points": False,
                    "tournament_id": auth_context.tournament.id,
                }
            ],
        }


@pytest.mark.asyncio(loop_scope="session")
async def test_create_ranking(
    session: AsyncSession, startup_and_shutdown_uvicorn_server: None, auth_context: AuthContext
) -> None:
    response = await send_tournament_request(HTTPMethod.POST, "rankings", auth_context, json={})
    assert response.get("success") is True, response

    tournament_id = auth_context.tournament.id
    for ranking in await get_all_rankings_in_tournament(session, tournament_id):
        if ranking.position != 0:
            await sql_delete_ranking(session, tournament_id, ranking.id)


@pytest.mark.asyncio(loop_scope="session")
async def test_delete_ranking(
    startup_and_shutdown_uvicorn_server: None, auth_context: AuthContext
) -> None:
    async with inserted_team(
        DUMMY_TEAM1.model_copy(update={"tournament_id": auth_context.tournament.id})
    ):
        async with inserted_ranking(
            DUMMY_RANKING1.model_copy(update={"tournament_id": auth_context.tournament.id})
        ) as ranking_inserted:
            assert (
                await send_tournament_request(
                    HTTPMethod.DELETE, f"rankings/{ranking_inserted.id}", auth_context
                )
                == SUCCESS_RESPONSE
            )


@pytest.mark.asyncio(loop_scope="session")
async def test_update_ranking(
    session: AsyncSession, startup_and_shutdown_uvicorn_server: None, auth_context: AuthContext
) -> None:
    body = {
        "win_points": "7.5",
        "draw_points": "2.5",
        "loss_points": "6.0",
        "add_score_points": True,
        "position": 42,
    }
    async with inserted_team(
        DUMMY_TEAM1.model_copy(update={"tournament_id": auth_context.tournament.id})
    ):
        async with inserted_ranking(
            DUMMY_RANKING1.model_copy(update={"tournament_id": auth_context.tournament.id})
        ) as ranking_inserted:
            response = await send_tournament_request(
                HTTPMethod.PUT, f"rankings/{ranking_inserted.id}", auth_context, json=body
            )
            updated_ranking = Ranking.model_validate(
                await session.scalar(
                    (
                        select(orm.Ranking).where(orm.Ranking.id == ranking_inserted.id)
                    ).execution_options(populate_existing=True)
                )
            )
            assert response["success"] is True
            assert updated_ranking.win_points == Decimal("7.5")


@pytest.mark.asyncio(loop_scope="session")
async def test_ranking_of_other_tournament_is_not_found(
    startup_and_shutdown_uvicorn_server: None, auth_context: AuthContext
) -> None:
    async with (
        inserted_tournament(
            DUMMY_TOURNAMENT.model_copy(
                update={"club_id": auth_context.club.id, "dashboard_endpoint": None}
            )
        ) as other_tournament,
        inserted_ranking(
            DUMMY_RANKING1.model_copy(update={"tournament_id": other_tournament.id})
        ) as other_ranking,
    ):
        body = {
            "win_points": "3",
            "draw_points": "1",
            "loss_points": "0",
            "add_score_points": False,
            "position": 0,
        }
        updated = await send_tournament_request(
            HTTPMethod.PUT, f"rankings/{other_ranking.id}", auth_context, json=body
        )
        deleted = await send_tournament_request(
            HTTPMethod.DELETE, f"rankings/{other_ranking.id}", auth_context
        )

    expected = {"detail": f"Could not find ranking with id {other_ranking.id}"}
    assert updated == deleted == expected


@pytest.mark.asyncio(loop_scope="session")
async def test_ranking_points_are_bounded(
    startup_and_shutdown_uvicorn_server: None, auth_context: AuthContext
) -> None:
    body = {"win_points": "1000000", "draw_points": "1", "loss_points": "-1000"}
    response = await send_tournament_request(HTTPMethod.POST, "rankings", auth_context, json=body)

    assert [error["loc"] for error in response["detail"]] == [["body", "win_points"]]


@pytest.mark.asyncio(loop_scope="session")
async def test_rankings_keep_a_position_each(
    session: AsyncSession, startup_and_shutdown_uvicorn_server: None, auth_context: AuthContext
) -> None:
    """
    New stage items take the first ranking, so two rankings must never share a position. Moving
    one makes room for it, and deleting one closes the gap.
    """
    tournament_id = auth_context.tournament.id
    for _ in range(2):
        await send_tournament_request(HTTPMethod.POST, "rankings", auth_context, json={})
    first, second, third = await get_all_rankings_in_tournament(session, tournament_id)
    body = {
        "win_points": "3",
        "draw_points": "1",
        "loss_points": "0",
        "add_score_points": False,
        "position": 0,
    }

    await send_tournament_request(HTTPMethod.PUT, f"rankings/{third.id}", auth_context, json=body)
    moved = await get_all_rankings_in_tournament(session, tournament_id)
    await send_tournament_request(HTTPMethod.DELETE, f"rankings/{third.id}", auth_context)
    await send_tournament_request(HTTPMethod.DELETE, f"rankings/{second.id}", auth_context)
    after = await get_all_rankings_in_tournament(session, tournament_id)

    assert [(ranking.id, ranking.position) for ranking in moved] == [
        (third.id, 0),
        (first.id, 1),
        (second.id, 2),
    ]
    assert [(ranking.id, ranking.position) for ranking in after] == [(first.id, 0)]
