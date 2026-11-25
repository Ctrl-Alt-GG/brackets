from http import HTTPMethod

import aiofiles
import aiofiles.os
import aiohttp
import pytest
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from bracket import orm
from bracket.logic.tournaments import delete_tournament
from bracket.models.db.tournament import Tournament
from bracket.models.enums import TournamentStatus
from bracket.sql.tournaments import (
    sql_delete_tournament,
    sql_get_tournament_by_endpoint_name,
    with_progress,
)
from bracket.utils.types import assert_some
from bracket.utils.uploads import UploadFolder, build_upload_path
from tests.dummy_records import DUMMY_MOCK_TIME, DUMMY_TOURNAMENT
from tests.integration_tests.api.shared import (
    SUCCESS_RESPONSE,
    send_auth_request,
    send_request,
    send_tournament_request,
)
from tests.integration_tests.models import AuthContext
from tests.integration_tests.sql import inserted_tournament
from tests.integration_tests.uploads import wait_until_removed


@pytest.mark.asyncio(loop_scope="session")
async def test_tournaments_endpoint(
    startup_and_shutdown_uvicorn_server: None, auth_context: AuthContext
) -> None:
    assert await send_auth_request(HTTPMethod.GET, "tournaments", auth_context, {}) == {
        "data": [
            {
                "id": auth_context.tournament.id,
                "created": DUMMY_MOCK_TIME.isoformat().replace("+00:00", "Z"),
                "start_time": DUMMY_MOCK_TIME.isoformat().replace("+00:00", "Z"),
                "name": "Some Cool Tournament",
                "logo_path": None,
                "dashboard_public": True,
                "dashboard_endpoint": "endpoint-test",
                "duration_minutes": 10,
                "margin_minutes": 5,
                "status": "OPEN",
                "matches_total": 0,
                "matches_played": 0,
                "last_match_end": None,
                "more_rounds_possible": False,
                "can_manage": True,
            }
        ],
    }


@pytest.mark.asyncio(loop_scope="session")
async def test_tournament_endpoint(
    startup_and_shutdown_uvicorn_server: None, auth_context: AuthContext
) -> None:
    assert await send_auth_request(
        HTTPMethod.GET, f"tournaments/{auth_context.tournament.id}", auth_context, {}
    ) == {
        "data": {
            "id": auth_context.tournament.id,
            "created": DUMMY_MOCK_TIME.isoformat().replace("+00:00", "Z"),
            "start_time": DUMMY_MOCK_TIME.isoformat().replace("+00:00", "Z"),
            "logo_path": None,
            "name": "Some Cool Tournament",
            "dashboard_public": True,
            "dashboard_endpoint": "endpoint-test",
            "duration_minutes": 10,
            "margin_minutes": 5,
            "status": "OPEN",
            "matches_total": 0,
            "matches_played": 0,
            "last_match_end": None,
            "more_rounds_possible": False,
        },
    }


@pytest.mark.asyncio(loop_scope="session")
async def test_create_tournament(
    session: AsyncSession, startup_and_shutdown_uvicorn_server: None, auth_context: AuthContext
) -> None:
    dashboard_endpoint = "some-new-endpoint"
    body = {
        "name": "Some new name",
        "start_time": DUMMY_MOCK_TIME.isoformat().replace("+00:00", "Z"),
        "dashboard_public": True,
        "dashboard_endpoint": dashboard_endpoint,
        "duration_minutes": 12,
        "margin_minutes": 3,
    }
    response = await send_auth_request(HTTPMethod.POST, "tournaments", auth_context, json=body)

    # Cleanup
    tournament = assert_some(await sql_get_tournament_by_endpoint_name(session, dashboard_endpoint))
    await delete_tournament(session, tournament.id)

    # The answer is the new tournament, so that the frontend can open it.
    assert response["data"]["id"] == tournament.id
    assert response["data"]["name"] == body["name"]


@pytest.mark.asyncio(loop_scope="session")
async def test_create_tournament_duplicate_dashboard_endpoint(
    startup_and_shutdown_uvicorn_server: None, auth_context: AuthContext
) -> None:
    body = {
        "name": "Some new name",
        "start_time": DUMMY_MOCK_TIME.isoformat().replace("+00:00", "Z"),
        "dashboard_public": True,
        "dashboard_endpoint": "endpoint-test",
        "duration_minutes": 12,
        "margin_minutes": 3,
    }
    assert await send_auth_request(HTTPMethod.POST, "tournaments", auth_context, json=body) == {
        "detail": "This Details link is already taken"
    }


@pytest.mark.asyncio(loop_scope="session")
async def test_update_tournament(
    session: AsyncSession, startup_and_shutdown_uvicorn_server: None, auth_context: AuthContext
) -> None:
    body = {
        "name": "Some new name",
        "start_time": DUMMY_MOCK_TIME.isoformat().replace("+00:00", "Z"),
        "dashboard_public": False,
        "duration_minutes": 12,
        "margin_minutes": 3,
    }
    assert (
        await send_tournament_request(HTTPMethod.PUT, "", auth_context, json=body)
        == SUCCESS_RESPONSE
    )
    updated_tournament = Tournament.model_validate(
        await session.scalar(
            (
                with_progress(
                    select(orm.Tournament).where(orm.Tournament.id == auth_context.tournament.id)
                )
            ).execution_options(populate_existing=True)
        )
    )
    assert updated_tournament.name == body["name"]
    assert updated_tournament.dashboard_public == body["dashboard_public"]


@pytest.mark.asyncio(loop_scope="session")
@pytest.mark.parametrize(
    ("dashboard_endpoint", "valid"),
    [
        ("summer-cup_2026", True),
        ("  padded  ", True),
        ("", True),
        ("2026", False),
        ("with space", False),
        ("a/b", False),
        ("x" * 65, False),
    ],
)
async def test_update_tournament_details_link(
    session: AsyncSession,
    startup_and_shutdown_uvicorn_server: None,
    auth_context: AuthContext,
    dashboard_endpoint: str,
    valid: bool,
) -> None:
    body = {
        "name": "  Some new name  ",
        "start_time": DUMMY_MOCK_TIME.isoformat().replace("+00:00", "Z"),
        "dashboard_public": True,
        "dashboard_endpoint": dashboard_endpoint,
        "duration_minutes": 12,
        "margin_minutes": 3,
    }
    response = await send_tournament_request(HTTPMethod.PUT, "", auth_context, json=body)
    updated_tournament = Tournament.model_validate(
        await session.scalar(
            (
                with_progress(
                    select(orm.Tournament).where(orm.Tournament.id == auth_context.tournament.id)
                )
            ).execution_options(populate_existing=True)
        )
    )
    await session.execute(
        update(orm.Tournament)
        .where(orm.Tournament.id == auth_context.tournament.id)
        .values(dashboard_endpoint=auth_context.tournament.dashboard_endpoint)
    )

    if valid:
        assert response == SUCCESS_RESPONSE
        assert updated_tournament.name == "Some new name"
        assert updated_tournament.dashboard_endpoint == (dashboard_endpoint.strip() or None)
    else:
        assert [error["loc"] for error in response["detail"]] == [["body", "dashboard_endpoint"]]


@pytest.mark.asyncio(loop_scope="session")
async def test_archive_and_unarchive_tournament(
    session: AsyncSession, startup_and_shutdown_uvicorn_server: None, auth_context: AuthContext
) -> None:
    # A tournament of its own, because other tests change the shared one's dashboard setting.
    async with inserted_tournament(
        DUMMY_TOURNAMENT.model_copy(update={"dashboard_endpoint": None}),
        auth_context.user.id,
    ) as tournament_inserted:
        tournament_context = auth_context.model_copy(update={"tournament": tournament_inserted})
        query = select(orm.Tournament).where(orm.Tournament.id == tournament_inserted.id)
        body = {"status": "ARCHIVED"}
        assert (
            await send_tournament_request(
                HTTPMethod.POST, "change-status", tournament_context, json=body
            )
            == SUCCESS_RESPONSE
        )
        updated_tournament = Tournament.model_validate(
            await session.scalar((with_progress(query)).execution_options(populate_existing=True))
        )
        assert updated_tournament.status is TournamentStatus.ARCHIVED
        # A public tournament stays public once archived.
        assert updated_tournament.dashboard_public is True

        # Archiving twice is not allowed
        assert await send_tournament_request(
            HTTPMethod.POST, "change-status", tournament_context, json=body
        ) == {"detail": "Tournament already has the requested status"}

        # Unarchive the tournament
        body = {"status": "OPEN"}
        assert (
            await send_tournament_request(
                HTTPMethod.POST, "change-status", tournament_context, json=body
            )
            == SUCCESS_RESPONSE
        )
        updated_tournament = Tournament.model_validate(
            await session.scalar((with_progress(query)).execution_options(populate_existing=True))
        )
        assert updated_tournament.status is TournamentStatus.OPEN
        assert updated_tournament.dashboard_public is True


@pytest.mark.asyncio(loop_scope="session")
async def test_delete_tournament(
    session: AsyncSession, startup_and_shutdown_uvicorn_server: None, auth_context: AuthContext
) -> None:
    async with inserted_tournament(
        DUMMY_TOURNAMENT.model_copy(update={"dashboard_endpoint": None}),
        auth_context.user.id,
    ) as tournament_inserted:
        assert (
            await send_tournament_request(
                HTTPMethod.DELETE,
                "",
                auth_context.model_copy(update={"tournament": tournament_inserted}),
            )
            == SUCCESS_RESPONSE
        )

    await sql_delete_tournament(session, tournament_inserted.id)


@pytest.mark.asyncio(loop_scope="session")
async def test_tournament_upload_and_remove_logo(
    startup_and_shutdown_uvicorn_server: None, auth_context: AuthContext
) -> None:
    test_file_path = "tests/integration_tests/assets/test_logo.png"
    data = aiohttp.FormData()
    data.add_field(
        "file",
        open(test_file_path, "rb"),  # pylint: disable=consider-using-with
        filename="test_logo.png",
        content_type="image/png",
    )

    response = await send_tournament_request(
        method=HTTPMethod.POST,
        endpoint="logo",
        auth_context=auth_context,
        body=data,
    )

    assert response.get("data", {}).get("logo_path"), f"Response: {response}"
    logo_path = build_upload_path(UploadFolder.TOURNAMENT_LOGOS, response["data"]["logo_path"])
    assert await aiofiles.os.path.exists(logo_path)

    response = await send_tournament_request(
        method=HTTPMethod.POST, endpoint="logo", auth_context=auth_context, body=aiohttp.FormData()
    )

    assert response["data"]["logo_path"] is None, f"Response: {response}"
    await wait_until_removed(logo_path)


UNAUTHORIZED_RESPONSE = {
    "detail": "Could not validate credentials or page is not publicly available"
}


@pytest.mark.asyncio(loop_scope="session")
async def test_non_public_tournament_endpoints_blocked_for_unauthenticated_users(
    startup_and_shutdown_uvicorn_server: None, auth_context: AuthContext
) -> None:
    """
    Unauthenticated requests to an archived tournament with dashboard_public=False must be
    rejected. Open tournaments are visible to everyone.
    This tests the fix for GHSA-9mjc-6fp2-hm9v.
    """
    async with inserted_tournament(
        DUMMY_TOURNAMENT.model_copy(
            update={
                "dashboard_public": False,
                "dashboard_endpoint": "non-public-endpoint",
                "status": TournamentStatus.ARCHIVED,
            }
        ),
        auth_context.user.id,
    ) as private_tournament:
        tournament_id = private_tournament.id
        for endpoint in (
            f"tournaments/{tournament_id}",
            f"tournaments/{tournament_id}/teams",
            f"tournaments/{tournament_id}/rankings",
            f"tournaments/{tournament_id}/stages?no_draft_rounds=true",
        ):
            response = await send_request(HTTPMethod.GET, endpoint)
            assert response == UNAUTHORIZED_RESPONSE, (
                f"Expected 401 for unauthenticated access to non-public endpoint {endpoint!r}, "
                f"got: {response}"
            )


@pytest.mark.asyncio(loop_scope="session")
async def test_archived_public_tournament_stays_public(
    startup_and_shutdown_uvicorn_server: None, auth_context: AuthContext
) -> None:
    async with (
        inserted_tournament(
            DUMMY_TOURNAMENT.model_copy(
                update={
                    "dashboard_endpoint": "archived-public-endpoint",
                    "status": TournamentStatus.ARCHIVED,
                }
            ),
            auth_context.user.id,
        ) as public_tournament,
        inserted_tournament(
            DUMMY_TOURNAMENT.model_copy(
                update={
                    "dashboard_public": False,
                    "dashboard_endpoint": None,
                    "status": TournamentStatus.ARCHIVED,
                }
            ),
            auth_context.user.id,
        ) as private_tournament,
    ):
        for filter_, expected in (("ALL", True), ("ARCHIVED", True), ("OPEN", False)):
            response = await send_request(HTTPMethod.GET, f"tournaments?filter_={filter_}")
            listed_ids = {tournament["id"] for tournament in response["data"]}
            assert (public_tournament.id in listed_ids) is expected, f"filter_={filter_}"
            assert private_tournament.id not in listed_ids, f"filter_={filter_}"

        response = await send_request(
            HTTPMethod.GET, "tournaments?endpoint_name=archived-public-endpoint"
        )
        assert [tournament["id"] for tournament in response["data"]] == [public_tournament.id]

        tournament_id = public_tournament.id
        for endpoint in (
            f"tournaments/{tournament_id}",
            f"tournaments/{tournament_id}/teams",
            f"tournaments/{tournament_id}/rankings",
            f"tournaments/{tournament_id}/stages?no_draft_rounds=true",
        ):
            response = await send_request(HTTPMethod.GET, endpoint)
            assert "data" in response, f"Expected {endpoint!r} to be public, got: {response}"


@pytest.mark.asyncio(loop_scope="session")
async def test_details_links_are_found_in_any_case(
    startup_and_shutdown_uvicorn_server: None, auth_context: AuthContext
) -> None:
    """Links printed or shared before Details links were lowercase still work, typed any way."""
    body = {
        "name": "Cup",
        "start_time": DUMMY_MOCK_TIME.isoformat().replace("+00:00", "Z"),
        "dashboard_public": True,
        "dashboard_endpoint": "Summer-Cup",
        "duration_minutes": 10,
        "margin_minutes": 5,
    }
    created = await send_auth_request(HTTPMethod.POST, "tournaments", auth_context, json=body)
    same_but_capitals = await send_auth_request(
        HTTPMethod.POST,
        "tournaments",
        auth_context,
        json={**body, "dashboard_endpoint": "SUMMER-cup"},
    )
    found = await send_request(HTTPMethod.GET, "tournaments?endpoint_name=SUMMER-CUP")
    unknown = await send_request(HTTPMethod.GET, "tournaments?endpoint_name=winter-cup")
    await send_auth_request(HTTPMethod.DELETE, f"tournaments/{created['data']['id']}", auth_context)

    assert created["data"]["dashboard_endpoint"] == "summer-cup"
    assert same_but_capitals == {"detail": "This Details link is already taken"}
    assert [tournament["id"] for tournament in found["data"]] == [created["data"]["id"]]
    assert unknown == {"detail": 'No tournament has the Details link "winter-cup"'}


@pytest.mark.asyncio(loop_scope="session")
async def test_organizers_also_see_the_public_tournaments_of_others(
    startup_and_shutdown_uvicorn_server: None, auth_context: AuthContext
) -> None:
    """At a LAN party, the organizer of one game follows another game's tournament too."""
    async with (
        inserted_tournament(
            DUMMY_TOURNAMENT.model_copy(update={"dashboard_endpoint": None})
        ) as public_tournament,
        inserted_tournament(
            DUMMY_TOURNAMENT.model_copy(
                update={
                    "dashboard_endpoint": None,
                    "dashboard_public": False,
                    "status": TournamentStatus.ARCHIVED,
                }
            )
        ) as private_tournament,
    ):
        response = await send_auth_request(HTTPMethod.GET, "tournaments?filter_=ALL", auth_context)

    listed = {tournament["id"]: tournament["can_manage"] for tournament in response["data"]}
    assert listed[auth_context.tournament.id] is True
    assert listed[public_tournament.id] is False
    assert private_tournament.id not in listed
