import pytest

from tests.utils import DEFAULT_PASSWORD, register_user


@pytest.mark.asyncio
async def test_register_creates_user_and_returns_tokens(client, unique_email):
    response = await client.post(
        "/api/v1/auth/register",
        json={"full_name": "Ada Lovelace", "email": unique_email, "password": DEFAULT_PASSWORD},
    )

    assert response.status_code == 201
    body = response.json()["data"]
    assert body["user"]["email"] == unique_email
    assert body["user"]["full_name"] == "Ada Lovelace"
    assert body["user"]["auth_provider"] == "email"
    assert body["user"]["is_verified"] is False
    assert body["tokens"]["access_token"]
    assert body["tokens"]["refresh_token"]
    assert body["tokens"]["token_type"] == "Bearer"


@pytest.mark.asyncio
async def test_register_rejects_duplicate_email(client, unique_email):
    await register_user(client, unique_email)

    response = await client.post(
        "/api/v1/auth/register",
        json={"full_name": "Someone Else", "email": unique_email, "password": DEFAULT_PASSWORD},
    )

    assert response.status_code == 409


@pytest.mark.asyncio
async def test_register_rejects_short_password(client, unique_email):
    response = await client.post(
        "/api/v1/auth/register",
        json={"full_name": "Ada Lovelace", "email": unique_email, "password": "short"},
    )

    assert response.status_code == 422


@pytest.mark.asyncio
async def test_register_rejects_invalid_email(client):
    response = await client.post(
        "/api/v1/auth/register",
        json={"full_name": "Ada Lovelace", "email": "not-an-email", "password": DEFAULT_PASSWORD},
    )

    assert response.status_code == 422


@pytest.mark.asyncio
async def test_register_rejects_missing_fields(client):
    response = await client.post("/api/v1/auth/register", json={"email": "x@example.com"})

    assert response.status_code == 422
