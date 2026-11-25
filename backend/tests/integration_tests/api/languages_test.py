"""The API answers in the language a request asks for with `Accept-Language`."""

from http import HTTPMethod

import aiohttp
import pytest

from bracket.utils.types import JsonDict
from tests.integration_tests.api.shared import get_root_uvicorn_url
from tests.integration_tests.models import AuthContext

HUNGARIAN = {"Accept-Language": "hu-HU,hu;q=0.9,en;q=0.8"}


async def tournament_request(
    auth_context: AuthContext,
    method: HTTPMethod,
    endpoint: str,
    json: JsonDict | None = None,
    headers: dict[str, str] | None = None,
) -> tuple[int, str, JsonDict]:
    """The status, the `Vary` header and the body of the answer."""
    async with (
        aiohttp.ClientSession() as session,
        session.request(
            method=str(method.value),
            url=f"{get_root_uvicorn_url()}tournaments/{auth_context.tournament.id}/{endpoint}",
            json=json,
            headers={**auth_context.headers, **(headers or {})},
        ) as response,
    ):
        body: JsonDict = await response.json()
        return response.status, response.headers.get("Vary", ""), body


@pytest.mark.asyncio(loop_scope="session")
async def test_messages_are_in_the_language_of_the_request(
    startup_and_shutdown_uvicorn_server: None, auth_context: AuthContext
) -> None:
    status, vary, body = await tournament_request(
        auth_context, HTTPMethod.DELETE, "rounds/999999", headers=HUNGARIAN
    )
    english = await tournament_request(auth_context, HTTPMethod.DELETE, "rounds/999999")

    assert (status, body) == (
        404,
        {"detail": "Nem található forduló ezzel az azonosítóval: 999999"},
    )
    # Caches keep the answers of each language apart.
    assert "Accept-Language" in vary
    # Without asking, a client gets English.
    assert english[2] == {"detail": "Could not find round with id 999999"}


@pytest.mark.asyncio(loop_scope="session")
async def test_field_checks_are_in_the_language_of_the_request(
    startup_and_shutdown_uvicorn_server: None, auth_context: AuthContext
) -> None:
    # The API's own check, and one that comes with Pydantic.
    own = await tournament_request(
        auth_context, HTTPMethod.POST, "teams_multi", {"names": " \n ", "active": True}, HUNGARIAN
    )
    missing = await tournament_request(
        auth_context, HTTPMethod.POST, "teams_multi", {"active": True}, HUNGARIAN
    )

    assert own[0] == missing[0] == 422
    assert [error["msg"] for error in own[2]["detail"]] == [
        "Value error, Adj meg legalább egy csapatot"
    ]
    assert [error["msg"] for error in missing[2]["detail"]] == ["Ezt a mezőt ki kell tölteni"]
