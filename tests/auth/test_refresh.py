import pytest

from api.v1.utils.jwt_tokens import create_refresh_token
from tests.utils import register_user


@pytest.mark.asyncio
async def test_refresh_returns_new_token_pair(client, unique_email):
    data = await register_user(client, unique_email)
    refresh_token = data["tokens"]["refresh_token"]

    response = await client.post("/api/v1/auth/refresh", json={"refresh_token": refresh_token})

    assert response.status_code == 200
    body = response.json()["data"]
    assert body["access_token"]
    assert body["refresh_token"]


@pytest.mark.asyncio
async def test_refresh_rejects_an_access_token_used_as_refresh(client, unique_email):
    data = await register_user(client, unique_email)
    access_token = data["tokens"]["access_token"]

    response = await client.post("/api/v1/auth/refresh", json={"refresh_token": access_token})

    assert response.status_code == 401


@pytest.mark.asyncio
async def test_refresh_rejects_malformed_token(client):
    response = await client.post("/api/v1/auth/refresh", json={"refresh_token": "not-a-real-jwt"})

    assert response.status_code == 401


@pytest.mark.asyncio
async def test_refresh_rejects_token_for_deleted_user(client):
    import uuid

    fake_refresh = create_refresh_token({"sub": str(uuid.uuid4()), "email": "ghost@example.com"})

    response = await client.post("/api/v1/auth/refresh", json={"refresh_token": fake_refresh})

    assert response.status_code == 401


@pytest.mark.asyncio
async def test_refresh_rejects_missing_field(client):
    response = await client.post("/api/v1/auth/refresh", json={})

    assert response.status_code == 422
