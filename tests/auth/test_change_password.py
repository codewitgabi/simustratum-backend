import pytest

from tests.utils import DEFAULT_PASSWORD, auth_header, register_user


@pytest.mark.asyncio
async def test_change_password_succeeds(client, unique_email):
    data = await register_user(client, unique_email)
    headers = auth_header(data["tokens"]["access_token"])

    response = await client.post(
        "/api/v1/auth/change-password",
        headers=headers,
        json={"current_password": DEFAULT_PASSWORD, "new_password": "a-new-strong-password"},
    )

    assert response.status_code == 200


@pytest.mark.asyncio
async def test_login_uses_new_password_after_change(client, unique_email):
    data = await register_user(client, unique_email)
    headers = auth_header(data["tokens"]["access_token"])

    await client.post(
        "/api/v1/auth/change-password",
        headers=headers,
        json={"current_password": DEFAULT_PASSWORD, "new_password": "a-new-strong-password"},
    )

    old_login = await client.post(
        "/api/v1/auth/login", json={"email": unique_email, "password": DEFAULT_PASSWORD}
    )
    new_login = await client.post(
        "/api/v1/auth/login", json={"email": unique_email, "password": "a-new-strong-password"}
    )

    assert old_login.status_code == 401
    assert new_login.status_code == 200


@pytest.mark.asyncio
async def test_change_password_rejects_wrong_current_password(client, unique_email):
    data = await register_user(client, unique_email)
    headers = auth_header(data["tokens"]["access_token"])

    response = await client.post(
        "/api/v1/auth/change-password",
        headers=headers,
        json={"current_password": "totally-wrong-password", "new_password": "a-new-strong-password"},
    )

    assert response.status_code == 401


@pytest.mark.asyncio
async def test_change_password_rejects_short_new_password(client, unique_email):
    data = await register_user(client, unique_email)
    headers = auth_header(data["tokens"]["access_token"])

    response = await client.post(
        "/api/v1/auth/change-password",
        headers=headers,
        json={"current_password": DEFAULT_PASSWORD, "new_password": "short"},
    )

    assert response.status_code == 422


@pytest.mark.asyncio
async def test_change_password_rejects_missing_fields(client, unique_email):
    data = await register_user(client, unique_email)
    headers = auth_header(data["tokens"]["access_token"])

    response = await client.post("/api/v1/auth/change-password", headers=headers, json={})

    assert response.status_code == 422


@pytest.mark.asyncio
async def test_change_password_rejects_google_only_account(client, unique_email, monkeypatch):
    async def _fake_verify(id_token: str):
        return {"sub": "google-sub-1", "email": unique_email, "name": "Grace Hopper"}

    monkeypatch.setattr("api.v1.services.auth._verify_google_id_token", _fake_verify)
    google_response = await client.post("/api/v1/auth/google", json={"id_token": "valid-token"})
    headers = auth_header(google_response.json()["data"]["tokens"]["access_token"])

    response = await client.post(
        "/api/v1/auth/change-password",
        headers=headers,
        json={"current_password": "anything", "new_password": "a-new-strong-password"},
    )

    assert response.status_code == 400


@pytest.mark.asyncio
async def test_change_password_requires_authentication(client):
    response = await client.post(
        "/api/v1/auth/change-password",
        json={"current_password": "x", "new_password": "a-new-strong-password"},
    )

    assert response.status_code in (401, 403)
