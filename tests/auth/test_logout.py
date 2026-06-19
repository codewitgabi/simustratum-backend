import pytest

from tests.utils import auth_header, register_user


@pytest.mark.asyncio
async def test_logout_succeeds_with_valid_token(client, unique_email):
    data = await register_user(client, unique_email)
    headers = auth_header(data["tokens"]["access_token"])

    response = await client.post("/api/v1/auth/logout", headers=headers)

    assert response.status_code == 200
    assert response.json()["success"] is True


@pytest.mark.asyncio
async def test_logged_out_token_can_no_longer_be_used(client, unique_email):
    data = await register_user(client, unique_email)
    headers = auth_header(data["tokens"]["access_token"])

    await client.post("/api/v1/auth/logout", headers=headers)

    response = await client.get("/api/v1/sessions", headers=headers)

    assert response.status_code == 401


@pytest.mark.asyncio
async def test_logout_without_a_token_is_rejected(client):
    response = await client.post("/api/v1/auth/logout")

    assert response.status_code in (401, 403)


@pytest.mark.asyncio
async def test_logout_with_garbage_token_is_rejected(client):
    response = await client.post(
        "/api/v1/auth/logout", headers={"Authorization": "Bearer not-a-real-jwt"}
    )

    assert response.status_code == 401


@pytest.mark.asyncio
async def test_double_logout_is_rejected_second_time(client, unique_email):
    data = await register_user(client, unique_email)
    headers = auth_header(data["tokens"]["access_token"])

    first = await client.post("/api/v1/auth/logout", headers=headers)
    second = await client.post("/api/v1/auth/logout", headers=headers)

    assert first.status_code == 200
    assert second.status_code == 401
