import uuid

import pytest

from tests.utils import create_session_via_api, registered_user_headers


@pytest.mark.asyncio
async def test_end_session_with_default_reason_marks_completed(client):
    headers = await registered_user_headers(client)
    session = await create_session_via_api(client, headers)

    response = await client.post(f"/api/v1/sessions/{session['id']}/end", headers=headers)

    assert response.status_code == 200
    body = response.json()["data"]
    assert body["status"] == "completed"
    assert body["ended_at"] is not None


@pytest.mark.asyncio
async def test_end_session_with_user_abandoned_reason(client):
    headers = await registered_user_headers(client)
    session = await create_session_via_api(client, headers)

    response = await client.post(
        f"/api/v1/sessions/{session['id']}/end", headers=headers, json={"reason": "user_abandoned"}
    )

    assert response.status_code == 200
    assert response.json()["data"]["status"] == "abandoned"


@pytest.mark.asyncio
async def test_end_session_is_idempotent_once_terminal(client):
    headers = await registered_user_headers(client)
    session = await create_session_via_api(client, headers)

    first = await client.post(f"/api/v1/sessions/{session['id']}/end", headers=headers)
    second = await client.post(
        f"/api/v1/sessions/{session['id']}/end", headers=headers, json={"reason": "user_abandoned"}
    )

    assert first.status_code == 200
    assert second.status_code == 200
    # status from the first call is preserved, not overwritten by the second call's reason
    assert second.json()["data"]["status"] == "completed"


@pytest.mark.asyncio
async def test_end_session_rejects_caller_who_does_not_own_it(client):
    owner_headers = await registered_user_headers(client)
    session = await create_session_via_api(client, owner_headers)

    other_headers = await registered_user_headers(client)
    response = await client.post(f"/api/v1/sessions/{session['id']}/end", headers=other_headers)

    assert response.status_code == 403


@pytest.mark.asyncio
async def test_end_session_404_for_unknown_session(client):
    headers = await registered_user_headers(client)

    response = await client.post(f"/api/v1/sessions/{uuid.uuid4()}/end", headers=headers)

    assert response.status_code == 404


@pytest.mark.asyncio
async def test_end_session_rejects_invalid_reason(client):
    headers = await registered_user_headers(client)
    session = await create_session_via_api(client, headers)

    response = await client.post(
        f"/api/v1/sessions/{session['id']}/end", headers=headers, json={"reason": "not_a_valid_reason"}
    )

    assert response.status_code == 422


@pytest.mark.asyncio
async def test_end_session_requires_authentication(client):
    response = await client.post(f"/api/v1/sessions/{uuid.uuid4()}/end")

    assert response.status_code in (401, 403)
