import uuid

import pytest

from api.v1.models.transcript_turn import SpeakerType
from tests.utils import create_session_via_api, insert_transcript_turn, registered_user_headers


@pytest.mark.asyncio
async def test_delete_session_removes_it_from_the_list(client):
    headers = await registered_user_headers(client)
    session = await create_session_via_api(client, headers)

    response = await client.delete(f"/api/v1/sessions/{session['id']}", headers=headers)
    assert response.status_code == 200

    listing = await client.get("/api/v1/sessions", headers=headers)
    assert all(item["id"] != session["id"] for item in listing.json()["data"]["items"])


@pytest.mark.asyncio
async def test_delete_session_cascades_to_transcript_turns(client):
    headers = await registered_user_headers(client)
    session = await create_session_via_api(client, headers)
    await insert_transcript_turn(session["id"], sequence=0, speaker_type=SpeakerType.PANELIST)

    response = await client.delete(f"/api/v1/sessions/{session['id']}", headers=headers)
    assert response.status_code == 200

    # Session is gone, so replay (which would otherwise prove turns were deleted too
    # via the FK cascade) now 404s instead of returning stale turns.
    replay = await client.get(f"/api/v1/sessions/{session['id']}/replay", headers=headers)
    assert replay.status_code == 404


@pytest.mark.asyncio
async def test_delete_session_twice_404s_on_the_second_call(client):
    headers = await registered_user_headers(client)
    session = await create_session_via_api(client, headers)

    first = await client.delete(f"/api/v1/sessions/{session['id']}", headers=headers)
    second = await client.delete(f"/api/v1/sessions/{session['id']}", headers=headers)

    assert first.status_code == 200
    assert second.status_code == 404


@pytest.mark.asyncio
async def test_delete_session_rejects_caller_who_does_not_own_it(client):
    owner_headers = await registered_user_headers(client)
    session = await create_session_via_api(client, owner_headers)

    other_headers = await registered_user_headers(client)
    response = await client.delete(f"/api/v1/sessions/{session['id']}", headers=other_headers)

    assert response.status_code == 403

    # Confirm it wasn't actually deleted by the forbidden attempt.
    still_there = await client.get("/api/v1/sessions", headers=owner_headers)
    assert any(item["id"] == session["id"] for item in still_there.json()["data"]["items"])


@pytest.mark.asyncio
async def test_delete_session_404_for_unknown_session(client):
    headers = await registered_user_headers(client)

    response = await client.delete(f"/api/v1/sessions/{uuid.uuid4()}", headers=headers)

    assert response.status_code == 404


@pytest.mark.asyncio
async def test_delete_session_requires_authentication(client):
    response = await client.delete(f"/api/v1/sessions/{uuid.uuid4()}")

    assert response.status_code in (401, 403)
