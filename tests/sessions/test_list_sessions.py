import pytest

from tests.utils import create_session_via_api, registered_user_headers


@pytest.mark.asyncio
async def test_list_sessions_returns_only_callers_sessions(client):
    headers_a = await registered_user_headers(client)
    headers_b = await registered_user_headers(client)

    await create_session_via_api(client, headers_a, topic="Session A1")
    await create_session_via_api(client, headers_a, topic="Session A2")
    await create_session_via_api(client, headers_b, topic="Session B1")

    response = await client.get("/api/v1/sessions", headers=headers_a)

    assert response.status_code == 200
    body = response.json()["data"]
    assert body["meta"]["total"] == 2
    titles = {item["title"] for item in body["items"]}
    assert titles == {"Session A1", "Session A2"}


@pytest.mark.asyncio
async def test_list_sessions_orders_newest_first(client):
    headers = await registered_user_headers(client)

    await create_session_via_api(client, headers, topic="Older")
    await create_session_via_api(client, headers, topic="Newer")

    response = await client.get("/api/v1/sessions", headers=headers)

    titles = [item["title"] for item in response.json()["data"]["items"]]
    assert titles == ["Newer", "Older"]


@pytest.mark.asyncio
async def test_list_sessions_pagination(client):
    headers = await registered_user_headers(client)
    for i in range(5):
        await create_session_via_api(client, headers, topic=f"Session {i}")

    response = await client.get("/api/v1/sessions", headers=headers, params={"page": 2, "limit": 2})

    assert response.status_code == 200
    body = response.json()["data"]
    assert len(body["items"]) == 2
    assert body["meta"] == {"total": 5, "page": 2, "limit": 2}


@pytest.mark.asyncio
async def test_list_sessions_rejects_invalid_page(client):
    headers = await registered_user_headers(client)

    response = await client.get("/api/v1/sessions", headers=headers, params={"page": 0})

    assert response.status_code == 422


@pytest.mark.asyncio
async def test_list_sessions_rejects_limit_above_max(client):
    headers = await registered_user_headers(client)

    response = await client.get("/api/v1/sessions", headers=headers, params={"limit": 101})

    assert response.status_code == 422


@pytest.mark.asyncio
async def test_list_sessions_empty_for_new_user(client):
    headers = await registered_user_headers(client)

    response = await client.get("/api/v1/sessions", headers=headers)

    assert response.status_code == 200
    assert response.json()["data"] == {"items": [], "meta": {"total": 0, "page": 1, "limit": 20}}


@pytest.mark.asyncio
async def test_list_sessions_requires_authentication(client):
    response = await client.get("/api/v1/sessions")

    assert response.status_code in (401, 403)
