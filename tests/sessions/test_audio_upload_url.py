import uuid

import pytest

from tests.utils import create_session_via_api, registered_user_headers, set_session_status


@pytest.mark.asyncio
async def test_audio_upload_url_succeeds_for_in_progress_session(client):
    headers = await registered_user_headers(client)
    session = await create_session_via_api(client, headers)
    await set_session_status(session["id"], "in_progress")

    response = await client.post(
        f"/api/v1/sessions/{session['id']}/turns/audio-upload-url",
        headers=headers,
        json={"turn_sequence": 0, "content_type": "audio/webm"},
    )

    assert response.status_code == 200
    body = response.json()["data"]
    assert body["upload_url"].startswith("https://api.cloudinary.com/v1_1/")
    assert body["storage_key"] == body["upload_params"]["public_id"]
    assert f"sessions/{session['id']}/turns/0/user-" in body["storage_key"]
    assert body["upload_params"]["type"] == "authenticated"
    assert body["upload_params"]["signature"]
    assert body["upload_params"]["api_key"]


@pytest.mark.asyncio
async def test_audio_upload_url_generates_unique_keys_per_call(client):
    headers = await registered_user_headers(client)
    session = await create_session_via_api(client, headers)
    await set_session_status(session["id"], "in_progress")

    first = await client.post(
        f"/api/v1/sessions/{session['id']}/turns/audio-upload-url",
        headers=headers,
        json={"turn_sequence": 0, "content_type": "audio/webm"},
    )
    second = await client.post(
        f"/api/v1/sessions/{session['id']}/turns/audio-upload-url",
        headers=headers,
        json={"turn_sequence": 0, "content_type": "audio/webm"},
    )

    assert first.json()["data"]["storage_key"] != second.json()["data"]["storage_key"]


@pytest.mark.asyncio
async def test_audio_upload_url_rejects_unsupported_content_type(client):
    headers = await registered_user_headers(client)
    session = await create_session_via_api(client, headers)
    await set_session_status(session["id"], "in_progress")

    response = await client.post(
        f"/api/v1/sessions/{session['id']}/turns/audio-upload-url",
        headers=headers,
        json={"turn_sequence": 0, "content_type": "video/mp4"},
    )

    assert response.status_code == 400


@pytest.mark.asyncio
async def test_audio_upload_url_rejects_pending_session(client):
    headers = await registered_user_headers(client)
    session = await create_session_via_api(client, headers)

    response = await client.post(
        f"/api/v1/sessions/{session['id']}/turns/audio-upload-url",
        headers=headers,
        json={"turn_sequence": 0, "content_type": "audio/webm"},
    )

    assert response.status_code == 409


@pytest.mark.asyncio
async def test_audio_upload_url_rejects_completed_session(client):
    headers = await registered_user_headers(client)
    session = await create_session_via_api(client, headers)
    await set_session_status(session["id"], "completed")

    response = await client.post(
        f"/api/v1/sessions/{session['id']}/turns/audio-upload-url",
        headers=headers,
        json={"turn_sequence": 0, "content_type": "audio/webm"},
    )

    assert response.status_code == 409


@pytest.mark.asyncio
async def test_audio_upload_url_rejects_non_owner(client):
    owner_headers = await registered_user_headers(client)
    session = await create_session_via_api(client, owner_headers)
    await set_session_status(session["id"], "in_progress")

    other_headers = await registered_user_headers(client)
    response = await client.post(
        f"/api/v1/sessions/{session['id']}/turns/audio-upload-url",
        headers=other_headers,
        json={"turn_sequence": 0, "content_type": "audio/webm"},
    )

    assert response.status_code == 403


@pytest.mark.asyncio
async def test_audio_upload_url_404_for_unknown_session(client):
    headers = await registered_user_headers(client)

    response = await client.post(
        f"/api/v1/sessions/{uuid.uuid4()}/turns/audio-upload-url",
        headers=headers,
        json={"turn_sequence": 0, "content_type": "audio/webm"},
    )

    assert response.status_code == 404


@pytest.mark.asyncio
async def test_audio_upload_url_requires_authentication(client):
    response = await client.post(
        f"/api/v1/sessions/{uuid.uuid4()}/turns/audio-upload-url",
        json={"turn_sequence": 0, "content_type": "audio/webm"},
    )

    assert response.status_code in (401, 403)
