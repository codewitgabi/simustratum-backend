import pytest

from tests.utils import DEFAULT_PASSWORD, register_user


@pytest.mark.asyncio
async def test_login_with_correct_credentials_returns_tokens(client, unique_email):
    await register_user(client, unique_email)

    response = await client.post(
        "/api/v1/auth/login", json={"email": unique_email, "password": DEFAULT_PASSWORD}
    )

    assert response.status_code == 200
    body = response.json()["data"]
    assert body["user"]["email"] == unique_email
    assert body["tokens"]["access_token"]
    assert body["tokens"]["refresh_token"]


@pytest.mark.asyncio
async def test_login_with_wrong_password_is_rejected(client, unique_email):
    await register_user(client, unique_email)

    response = await client.post(
        "/api/v1/auth/login", json={"email": unique_email, "password": "wrong-password"}
    )

    assert response.status_code == 401


@pytest.mark.asyncio
async def test_login_with_unknown_email_is_rejected(client):
    response = await client.post(
        "/api/v1/auth/login", json={"email": "nobody@example.com", "password": DEFAULT_PASSWORD}
    )

    assert response.status_code == 401


@pytest.mark.asyncio
async def test_login_rejects_malformed_email(client):
    response = await client.post(
        "/api/v1/auth/login", json={"email": "not-an-email", "password": DEFAULT_PASSWORD}
    )

    assert response.status_code == 422


@pytest.mark.asyncio
async def test_login_against_google_only_account_is_rejected(client, unique_email, monkeypatch):
    async def _fake_verify(id_token: str):
        return {"sub": "google-sub-123", "email": unique_email, "name": "Google User"}

    monkeypatch.setattr("api.v1.services.auth._verify_google_id_token", _fake_verify)
    google_response = await client.post("/api/v1/auth/google", json={"id_token": "anything"})
    assert google_response.status_code == 200

    response = await client.post(
        "/api/v1/auth/login", json={"email": unique_email, "password": DEFAULT_PASSWORD}
    )

    assert response.status_code == 401
