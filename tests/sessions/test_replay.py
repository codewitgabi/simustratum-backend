import uuid

import pytest

from api.v1.models.transcript_turn import SpeakerType
from tests.utils import create_session_via_api, insert_transcript_turn, registered_user_headers, set_session_status


@pytest.mark.asyncio
async def test_replay_returns_turns_in_order_with_resolved_user_audio(client):
    headers = await registered_user_headers(client)
    session = await create_session_via_api(client, headers)
    await set_session_status(session["id"], "completed")

    await insert_transcript_turn(
        session["id"],
        sequence=0,
        speaker_type=SpeakerType.PANELIST,
        panelist_id=session["panelists"][0]["id"],
        text="Tell me about your methodology.",
        gesture_sequence=[{"t_ms": 100, "gesture": "nod"}],
    )
    await insert_transcript_turn(
        session["id"],
        sequence=1,
        speaker_type=SpeakerType.USER,
        text="It's a mixed-methods approach.",
        audio_storage_key="sessions/abc/turns/1/user-xyz",
        ended_at_ms=4200,
    )

    response = await client.get(f"/api/v1/sessions/{session['id']}/replay", headers=headers)

    assert response.status_code == 200
    body = response.json()["data"]
    assert body["session_id"] == session["id"]
    assert body["status"] == "completed"
    assert len(body["turns"]) == 2

    panelist_turn, user_turn = body["turns"]
    assert panelist_turn["speaker_type"] == "panelist"
    assert panelist_turn["audio_url"] is None
    assert panelist_turn["gesture_sequence"] == [{"t_ms": 100, "gesture": "nod"}]

    assert user_turn["speaker_type"] == "user"
    assert user_turn["audio_url"] is not None
    assert "sessions/abc/turns/1/user-xyz" in user_turn["audio_url"]
    assert user_turn["ended_at_ms"] == 4200


@pytest.mark.asyncio
async def test_replay_user_turn_without_recording_has_null_audio(client):
    """Covers a pre-existing session predating this feature: no storage key, no error."""
    headers = await registered_user_headers(client)
    session = await create_session_via_api(client, headers)
    await set_session_status(session["id"], "completed")

    await insert_transcript_turn(
        session["id"],
        sequence=0,
        speaker_type=SpeakerType.USER,
        text="An answer with no recording on file.",
        audio_storage_key=None,
    )

    response = await client.get(f"/api/v1/sessions/{session['id']}/replay", headers=headers)

    assert response.status_code == 200
    turn = response.json()["data"]["turns"][0]
    assert turn["audio_url"] is None
    assert turn["text"] == "An answer with no recording on file."


@pytest.mark.asyncio
async def test_replay_rejects_pending_session(client):
    headers = await registered_user_headers(client)
    session = await create_session_via_api(client, headers)

    response = await client.get(f"/api/v1/sessions/{session['id']}/replay", headers=headers)

    assert response.status_code == 409


@pytest.mark.asyncio
async def test_replay_rejects_in_progress_session(client):
    headers = await registered_user_headers(client)
    session = await create_session_via_api(client, headers)
    await set_session_status(session["id"], "in_progress")

    response = await client.get(f"/api/v1/sessions/{session['id']}/replay", headers=headers)

    assert response.status_code == 409


@pytest.mark.asyncio
async def test_replay_allows_abandoned_session(client):
    headers = await registered_user_headers(client)
    session = await create_session_via_api(client, headers)
    await set_session_status(session["id"], "abandoned")

    response = await client.get(f"/api/v1/sessions/{session['id']}/replay", headers=headers)

    assert response.status_code == 200
    assert response.json()["data"]["status"] == "abandoned"


@pytest.mark.asyncio
async def test_replay_rejects_non_owner(client):
    owner_headers = await registered_user_headers(client)
    session = await create_session_via_api(client, owner_headers)
    await set_session_status(session["id"], "completed")

    other_headers = await registered_user_headers(client)
    response = await client.get(f"/api/v1/sessions/{session['id']}/replay", headers=other_headers)

    assert response.status_code == 403


@pytest.mark.asyncio
async def test_replay_404_for_unknown_session(client):
    headers = await registered_user_headers(client)

    response = await client.get(f"/api/v1/sessions/{uuid.uuid4()}/replay", headers=headers)

    assert response.status_code == 404


@pytest.mark.asyncio
async def test_replay_requires_authentication(client):
    response = await client.get(f"/api/v1/sessions/{uuid.uuid4()}/replay")

    assert response.status_code in (401, 403)
