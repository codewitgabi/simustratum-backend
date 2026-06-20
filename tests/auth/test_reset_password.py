from urllib.parse import parse_qs, urlparse

import pytest

from tests.utils import DEFAULT_PASSWORD, register_user


def _extract_token(reset_link: str) -> str:
    return parse_qs(urlparse(reset_link).query)["token"][0]


@pytest.mark.asyncio
async def test_reset_password_succeeds_and_new_password_works(client, unique_email, captured_emails):
    await register_user(client, unique_email)
    await client.post("/api/v1/auth/forgot-password", json={"email": unique_email})
    token = _extract_token(captured_emails[0]["reset_link"])

    response = await client.post(
        "/api/v1/auth/reset-password", json={"token": token, "new_password": "a-new-strong-password"}
    )
    assert response.status_code == 200

    old_login = await client.post(
        "/api/v1/auth/login", json={"email": unique_email, "password": DEFAULT_PASSWORD}
    )
    new_login = await client.post(
        "/api/v1/auth/login", json={"email": unique_email, "password": "a-new-strong-password"}
    )
    assert old_login.status_code == 401
    assert new_login.status_code == 200


@pytest.mark.asyncio
async def test_reset_password_token_is_single_use(client, unique_email, captured_emails):
    await register_user(client, unique_email)
    await client.post("/api/v1/auth/forgot-password", json={"email": unique_email})
    token = _extract_token(captured_emails[0]["reset_link"])

    first = await client.post(
        "/api/v1/auth/reset-password", json={"token": token, "new_password": "a-new-strong-password"}
    )
    second = await client.post(
        "/api/v1/auth/reset-password", json={"token": token, "new_password": "another-strong-password"}
    )

    assert first.status_code == 200
    assert second.status_code == 400


@pytest.mark.asyncio
async def test_reset_password_rejects_invalid_token(client):
    response = await client.post(
        "/api/v1/auth/reset-password",
        json={"token": "not-a-real-token", "new_password": "a-new-strong-password"},
    )

    assert response.status_code == 400


@pytest.mark.asyncio
async def test_reset_password_rejects_expired_token(client, unique_email, captured_emails, monkeypatch):
    monkeypatch.setattr("api.v1.services.auth.config.PASSWORD_RESET_TOKEN_EXPIRE_MINUTES", -1)
    await register_user(client, unique_email)
    await client.post("/api/v1/auth/forgot-password", json={"email": unique_email})
    token = _extract_token(captured_emails[0]["reset_link"])

    response = await client.post(
        "/api/v1/auth/reset-password", json={"token": token, "new_password": "a-new-strong-password"}
    )

    assert response.status_code == 400


@pytest.mark.asyncio
async def test_reset_password_rejects_short_new_password(client, unique_email, captured_emails):
    await register_user(client, unique_email)
    await client.post("/api/v1/auth/forgot-password", json={"email": unique_email})
    token = _extract_token(captured_emails[0]["reset_link"])

    response = await client.post(
        "/api/v1/auth/reset-password", json={"token": token, "new_password": "short"}
    )

    assert response.status_code == 422


@pytest.mark.asyncio
async def test_reset_password_rejects_missing_fields(client):
    response = await client.post("/api/v1/auth/reset-password", json={})

    assert response.status_code == 422
