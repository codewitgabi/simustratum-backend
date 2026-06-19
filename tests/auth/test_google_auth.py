import pytest

from tests.utils import DEFAULT_PASSWORD, register_user


def _stub_google_verify(monkeypatch, payload: dict):
    async def _fake_verify(id_token: str):
        return payload

    monkeypatch.setattr("api.v1.services.auth._verify_google_id_token", _fake_verify)


@pytest.mark.asyncio
async def test_google_auth_creates_new_user(client, unique_email, monkeypatch):
    _stub_google_verify(
        monkeypatch, {"sub": "google-sub-1", "email": unique_email, "name": "Grace Hopper"}
    )

    response = await client.post("/api/v1/auth/google", json={"id_token": "valid-token"})

    assert response.status_code == 200
    body = response.json()["data"]
    assert body["user"]["email"] == unique_email
    assert body["user"]["auth_provider"] == "google"
    assert body["user"]["is_verified"] is True
    assert body["tokens"]["access_token"]


@pytest.mark.asyncio
async def test_google_auth_links_existing_email_account(client, unique_email, monkeypatch):
    await register_user(client, unique_email)
    _stub_google_verify(
        monkeypatch, {"sub": "google-sub-2", "email": unique_email, "name": "Grace Hopper"}
    )

    response = await client.post("/api/v1/auth/google", json={"id_token": "valid-token"})

    assert response.status_code == 200
    body = response.json()["data"]
    assert body["user"]["email"] == unique_email

    # the linked account can now also log in with its original password
    login_response = await client.post(
        "/api/v1/auth/login", json={"email": unique_email, "password": DEFAULT_PASSWORD}
    )
    assert login_response.status_code == 200


@pytest.mark.asyncio
async def test_google_auth_rejects_invalid_token(client, monkeypatch):
    async def _fake_verify(id_token: str):
        from fastapi import HTTPException, status

        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid Google token")

    monkeypatch.setattr("api.v1.services.auth._verify_google_id_token", _fake_verify)

    response = await client.post("/api/v1/auth/google", json={"id_token": "garbage"})

    assert response.status_code == 401


@pytest.mark.asyncio
async def test_google_auth_rejects_payload_missing_email(client, monkeypatch):
    _stub_google_verify(monkeypatch, {"sub": "google-sub-3"})

    response = await client.post("/api/v1/auth/google", json={"id_token": "valid-token"})

    assert response.status_code == 401


@pytest.mark.asyncio
async def test_google_auth_rejects_missing_id_token_field(client):
    response = await client.post("/api/v1/auth/google", json={})

    assert response.status_code == 422
