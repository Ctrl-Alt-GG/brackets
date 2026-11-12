from http import HTTPMethod
from uuid import uuid4

import aiohttp
import jwt
import pytest
from heliclockter import datetime_utc, timedelta

from bracket.config import config
from bracket.database import engine
from bracket.models.db.account import UserAccountType
from bracket.routes.auth import CSRF_HEADER, CSRF_HEADER_VALUE, SESSION_COOKIE, get_auth_hash
from bracket.sql.clubs import sql_delete_club
from bracket.utils.dummy_records import DUMMY_CLUB, DUMMY_TOURNAMENT
from bracket.utils.rate_limit import (
    get_account_lockout_key,
    get_account_lockout_retry_after,
    record_account_failure,
    reset_account_failures,
)
from bracket.utils.types import JsonDict
from tests.integration_tests.api.shared import (
    get_root_uvicorn_url,
    send_auth_request,
    send_request,
)
from tests.integration_tests.mocks import get_mock_token, get_mock_user
from tests.integration_tests.models import AuthContext
from tests.integration_tests.sql import inserted_club, inserted_tournament, inserted_user


@pytest.mark.asyncio(loop_scope="session")
async def test_get_token_success(startup_and_shutdown_uvicorn_server: None) -> None:
    mock_user = get_mock_user()
    body = {
        "username": mock_user.email,
        "password": "mypassword",
    }
    async with inserted_user(mock_user) as user_inserted:
        response = JsonDict(await send_request(HTTPMethod.POST, "token", body))
        # The mock user's bcrypt hash is replaced by an Argon2 one on login, and the token must
        # already belong to the new hash.
        headers = {"Authorization": f"Bearer {response['access_token']}"}
        me = await send_request(HTTPMethod.GET, "users/me", None, None, headers)

    assert response.get("token_type") == "bearer"
    assert response.get("user_id") == user_inserted.id
    assert me["data"]["id"] == user_inserted.id

    decoded = jwt.decode(
        response["access_token"],
        config.jwt_secret,
        algorithms=["HS256"],
        audience=config.jwt_audience,
        issuer=config.jwt_issuer,
    )
    assert decoded["sub"] == str(user_inserted.id)
    assert decoded["type"] == "access"
    assert decoded["exp"] - decoded["iat"] == config.access_token_expire_minutes * 60


@pytest.mark.asyncio(loop_scope="session")
async def test_get_token_invalid_credentials(startup_and_shutdown_uvicorn_server: None) -> None:
    mock_user = get_mock_user()
    body = {
        "username": mock_user.email,
        "password": "invalid password",
    }
    async with inserted_user(mock_user):
        response = JsonDict(await send_request(HTTPMethod.POST, "token", body))

    assert response == {"detail": "Incorrect email or password"}


@pytest.mark.asyncio(loop_scope="session")
async def test_auth_on_protected_endpoint(startup_and_shutdown_uvicorn_server: None) -> None:
    mock_user = get_mock_user()

    async with inserted_user(mock_user) as user_inserted:
        headers = {"Authorization": f"Bearer {get_mock_token(user_inserted)}"}
        response = JsonDict(
            await send_request(HTTPMethod.GET, f"users/{user_inserted.id}", {}, None, headers)
        )

        assert response == {
            "data": {
                "id": user_inserted.id,
                "email": user_inserted.email,
                "name": user_inserted.name,
                "created": "2000-01-01T00:00:00Z",
                "account_type": UserAccountType.REGULAR.value,
            }
        }


@pytest.mark.asyncio(loop_scope="session")
async def test_invalid_token(startup_and_shutdown_uvicorn_server: None) -> None:
    headers = {"Authorization": "Bearer some.invalid.token"}

    response = JsonDict(await send_request(HTTPMethod.GET, "users/me", {}, None, headers))
    assert response == {"detail": "Could not validate credentials"}


@pytest.mark.asyncio(loop_scope="session")
@pytest.mark.parametrize(
    "claims",
    [
        {"aud": "another-api"},
        {"iss": "https://another-issuer.example.org"},
        {"type": "refresh"},
        {"sub": "someone@example.org"},
        {"nbf": datetime_utc.now() + timedelta(hours=1)},
        # Issued before the password changed.
        {"auth_hash": get_auth_hash("$argon2id$an-old-password-hash")},
    ],
)
async def test_signed_token_with_wrong_claims(
    startup_and_shutdown_uvicorn_server: None, auth_context: AuthContext, claims: JsonDict
) -> None:
    """Every token that fails validation is rejected the same way, instead of crashing."""
    now = datetime_utc.now()
    token = jwt.encode(
        {
            "sub": str(auth_context.user.id),
            "aud": config.jwt_audience,
            "iss": config.jwt_issuer,
            "iat": now,
            "nbf": now,
            "exp": now + timedelta(minutes=5),
            "type": "access",
            "auth_hash": get_auth_hash(auth_context.user.password_hash),
            **claims,
        },
        config.jwt_secret,
        algorithm="HS256",
    )
    headers = {"Authorization": f"Bearer {token}"}

    response = JsonDict(await send_request(HTTPMethod.GET, "users/me", {}, None, headers))
    assert response == {"detail": "Could not validate credentials"}


@pytest.mark.asyncio(loop_scope="session")
async def test_not_authenticated_for_tournament(
    startup_and_shutdown_uvicorn_server: None, auth_context: AuthContext
) -> None:
    async with inserted_club(
        DUMMY_CLUB.model_copy(update={"name": f"Another club {uuid4()}"})
    ) as club_inserted:
        async with inserted_tournament(
            DUMMY_TOURNAMENT.model_copy(
                update={"club_id": club_inserted.id, "dashboard_endpoint": "some-slug"}
            )
        ) as tournament_inserted:
            response = JsonDict(
                await send_auth_request(
                    HTTPMethod.GET,
                    f"tournaments/{tournament_inserted.id}/available_inputs",
                    auth_context,
                )
            )
    # A valid session that may not do this is refused, not signed out.
    assert response == {"detail": "You don't have access to this tournament"}


@pytest.mark.asyncio(loop_scope="session")
async def test_session_cookie(startup_and_shutdown_uvicorn_server: None) -> None:
    """The frontend signs in with an HttpOnly cookie, which needs the CSRF header to change data."""
    mock_user = get_mock_user()
    csrf_headers = {CSRF_HEADER: CSRF_HEADER_VALUE}

    async with (
        inserted_user(mock_user),
        # Cookies of a host that is an IP address are only kept by an "unsafe" cookie jar.
        aiohttp.ClientSession(cookie_jar=aiohttp.CookieJar(unsafe=True)) as session,
    ):
        url = get_root_uvicorn_url()
        login = await session.post(
            f"{url}token", data={"username": mock_user.email, "password": "mypassword"}
        )
        set_cookie = login.headers["Set-Cookie"]
        me = await (await session.get(f"{url}users/me")).json()
        without_csrf_header = await session.post(f"{url}clubs", json={"name": f"Club {uuid4()}"})
        with_csrf_header = await session.post(
            f"{url}clubs", json={"name": f"Club {uuid4()}"}, headers=csrf_headers
        )
        club = await with_csrf_header.json()
        logout = await session.post(f"{url}logout", headers=csrf_headers)
        after_logout = await session.get(f"{url}users/me")
        async with engine.begin() as conn:
            await sql_delete_club(conn, club["data"]["id"])

    assert set_cookie.startswith(f"{SESSION_COOKIE}=")
    assert "HttpOnly" in set_cookie
    assert "SameSite=strict" in set_cookie
    assert me["data"]["email"] == mock_user.email
    assert without_csrf_header.status == 403
    assert with_csrf_header.status == 200
    assert logout.status == 204
    assert after_logout.status == 401


@pytest.mark.asyncio(loop_scope="session")
async def test_logout_ends_the_session_for_copied_tokens(
    startup_and_shutdown_uvicorn_server: None,
) -> None:
    """Logging out removes the cookie, and also stops a token that was copied before."""
    mock_user = get_mock_user()
    url = get_root_uvicorn_url()

    async with inserted_user(mock_user), aiohttp.ClientSession() as session:
        login = await session.post(
            f"{url}token", data={"username": mock_user.email, "password": "mypassword"}
        )
        headers = {"Authorization": f"Bearer {(await login.json())['access_token']}"}
        before = await session.get(f"{url}users/me", headers=headers)
        logout = await session.post(f"{url}logout", headers=headers)
        after = await session.get(f"{url}users/me", headers=headers)

    assert before.status == 200
    assert logout.status == 204
    assert after.status == 401


@pytest.mark.asyncio(loop_scope="session")
async def test_frontend_login_keeps_the_token_out_of_the_body(
    startup_and_shutdown_uvicorn_server: None,
) -> None:
    """The frontend's session is the cookie, so it gets no token that a script could read."""
    mock_user = get_mock_user()

    async with inserted_user(mock_user), aiohttp.ClientSession() as session:
        login = await session.post(
            f"{get_root_uvicorn_url()}token",
            data={"username": mock_user.email, "password": "mypassword"},
            headers={CSRF_HEADER: CSRF_HEADER_VALUE},
        )
        body = await login.json()

    assert body["access_token"] == ""
    assert body["name"] == mock_user.name
    assert login.headers["Set-Cookie"].startswith(f"{SESSION_COOKIE}=")


@pytest.mark.asyncio(loop_scope="session")
async def test_login_from_another_site_is_refused(
    startup_and_shutdown_uvicorn_server: None,
) -> None:
    """Another site can't sign a visitor in to an account of its choosing (login CSRF)."""
    mock_user = get_mock_user()
    credentials = {"username": mock_user.email, "password": "mypassword"}
    url = f"{get_root_uvicorn_url()}token"

    async with inserted_user(mock_user), aiohttp.ClientSession() as session:
        statuses = [
            (await session.post(url, data=credentials, headers=headers)).status
            for headers in (
                {"Sec-Fetch-Site": "cross-site"},
                # Browsers without Sec-Fetch-Site still say where the request comes from.
                {"Origin": "https://evil.example"},
                {"Sec-Fetch-Site": "same-origin", "Origin": "https://evil.example"},
                # A compromised sibling host is same-site, but still can't sign this host in.
                {"Sec-Fetch-Site": "same-site", "Origin": "https://evil.example"},
                {"Sec-Fetch-Site": "same-site", "Origin": config.base_url},
                {"Origin": config.base_url},
                {},
            )
        ]

    assert statuses == [403, 403, 403, 403, 200, 200, 200]


@pytest.mark.asyncio(loop_scope="session")
async def test_session_cookie_is_renewed_while_it_is_used(
    startup_and_shutdown_uvicorn_server: None, monkeypatch: pytest.MonkeyPatch
) -> None:
    """
    A session past half its life gets a new cookie, so an organizer who keeps working isn't
    signed out in the middle of an event. A bearer token is left alone.
    """
    mock_user = get_mock_user()
    url = get_root_uvicorn_url()

    async with (
        inserted_user(mock_user),
        aiohttp.ClientSession(cookie_jar=aiohttp.CookieJar(unsafe=True)) as session,
    ):
        login = await session.post(
            f"{url}token", data={"username": mock_user.email, "password": "mypassword"}
        )
        token = (await login.json())["access_token"]
        fresh = await session.get(f"{url}users/me")

        # The same session, seen from a server on which sessions last twice as long: past half.
        monkeypatch.setattr(
            config, "access_token_expire_minutes", config.access_token_expire_minutes * 2 + 2
        )
        used = await session.get(f"{url}users/me")
        async with aiohttp.ClientSession() as api_client:
            with_bearer = await api_client.get(
                f"{url}users/me", headers={"Authorization": f"Bearer {token}"}
            )

    assert "Set-Cookie" not in fresh.headers
    assert used.headers["Set-Cookie"].startswith(f"{SESSION_COOKIE}=")
    assert with_bearer.status == 200
    assert "Set-Cookie" not in with_bearer.headers


def test_failed_logins_are_counted_per_account_and_address() -> None:
    """Someone failing on purpose only locks out their own address, not the organizer's."""
    organizer = get_account_lockout_key("organizer@example.org", address="203.0.113.7")
    attacker = get_account_lockout_key("organizer@example.org", address="198.51.100.9")

    for _ in range(6):
        record_account_failure(attacker)

    try:
        assert get_account_lockout_retry_after(attacker) is not None
        assert get_account_lockout_retry_after(organizer) is None
    finally:
        reset_account_failures(attacker)
