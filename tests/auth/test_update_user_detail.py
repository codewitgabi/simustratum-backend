import pytest

from tests.utils import auth_header, register_user


@pytest.mark.asyncio
async def test_update_full_name_succeeds(client, unique_email):
    data = await register_user(client, unique_email)
    headers = auth_header(data["tokens"]["access_token"])

    response = await client.patch(
        "/api/v1/auth/me", headers=headers, json={"full_name": "New Full Name"}
    )

    assert response.status_code == 200
    body = response.json()["data"]
    assert body["full_name"] == "New Full Name"
    assert body["email"] == unique_email


@pytest.mark.asyncio
async def test_update_full_name_persists(client, unique_email):
    data = await register_user(client, unique_email)
    headers = auth_header(data["tokens"]["access_token"])

    await client.patch("/api/v1/auth/me", headers=headers, json={"full_name": "Persisted Name"})
    login = await client.post(
        "/api/v1/auth/login", json={"email": unique_email, "password": "correct-password-123"}
    )

    assert login.json()["data"]["user"]["full_name"] == "Persisted Name"


@pytest.mark.asyncio
async def test_update_full_name_rejects_blank_name(client, unique_email):
    data = await register_user(client, unique_email)
    headers = auth_header(data["tokens"]["access_token"])

    response = await client.patch("/api/v1/auth/me", headers=headers, json={"full_name": "   "})

    assert response.status_code == 422


@pytest.mark.asyncio
async def test_update_full_name_rejects_missing_field(client, unique_email):
    data = await register_user(client, unique_email)
    headers = auth_header(data["tokens"]["access_token"])

    response = await client.patch("/api/v1/auth/me", headers=headers, json={})

    assert response.status_code == 422


@pytest.mark.asyncio
async def test_update_full_name_requires_authentication(client):
    response = await client.patch("/api/v1/auth/me", json={"full_name": "No Auth"})

    assert response.status_code in (401, 403)
