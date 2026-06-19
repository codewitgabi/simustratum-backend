"""
The /sessions/{id}/stream WebSocket can't be driven with httpx's ASGITransport
(HTTP-only), so this file uses Starlette's TestClient instead — sync tests, real
ASGI app, real DB, same external-service stubs as everywhere else.
"""

import uuid

import pytest
from fastapi.testclient import TestClient
from starlette.websockets import WebSocketDisconnect

from api.v1.services.session_orchestrator import QUESTION_LIMIT
from tests.utils import DEFAULT_PASSWORD


@pytest.fixture
def ws_client():
    from main import app

    # Deliberately not using `with TestClient(app) as ...` — that triggers the
    # app's lifespan, which calls qdrant_client.connect() and makes a real
    # network call. Nothing under test depends on lifespan having run.
    yield TestClient(app)


def _register(client: TestClient) -> dict:
    email = f"user-{uuid.uuid4().hex[:12]}@example.com"
    response = client.post(
        "/api/v1/auth/register",
        json={"full_name": "WS Tester", "email": email, "password": DEFAULT_PASSWORD},
    )
    assert response.status_code == 201
    return response.json()["data"]


def _create_session(client: TestClient, access_token: str, **option_overrides: bool) -> dict:
    body = {
        "scenario": "project_defense",
        "topic": "A study on distributed consensus",
        "panelists": [
            {"name": "Dr. Okafor", "role": "Methods", "strictness": 70, "inquisitiveness": 60},
        ],
        "real_time_feedback": True,
        "answer_timer": True,
        "save_transcript": True,
    }
    body.update(option_overrides)
    response = client.post(
        "/api/v1/sessions",
        headers={"Authorization": f"Bearer {access_token}"},
        json=body,
    )
    assert response.status_code == 201
    return response.json()["data"]


def _stream_url(session_id: str, token: str) -> str:
    return f"/api/v1/sessions/{session_id}/stream?token={token}"


def test_connect_sends_initial_session_state_and_starts_session(ws_client, stub_external_services):
    user = _register(ws_client)
    token = user["tokens"]["access_token"]
    session = _create_session(ws_client, token)

    with ws_client.websocket_connect(_stream_url(session["id"], token)) as ws:
        message = ws.receive_json()

    assert message["type"] == "session_state"
    assert message["payload"]["status"] == "in_progress"
    assert message["payload"]["question_count"] == 0
    assert message["payload"]["awaiting_user_response"] is True
    assert message["payload"]["current_panelist_id"] is None


def test_user_response_triggers_score_update_and_next_question(ws_client, stub_external_services):
    user = _register(ws_client)
    token = user["tokens"]["access_token"]
    session = _create_session(ws_client, token)

    with ws_client.websocket_connect(_stream_url(session["id"], token)) as ws:
        ws.receive_json()  # initial session_state

        ws.send_json({"type": "user_response", "text": "My opening answer.", "duration_ms": 3000})

        score_message = ws.receive_json()
        assert score_message["type"] == "score_update"
        assert score_message["payload"]["question_count"] == 1
        for key in ("clarity", "confidence", "structure"):
            assert 0 <= score_message["payload"][key] <= 100

        question_message = ws.receive_json()
        assert question_message["type"] == "panelist_question"
        assert question_message["payload"]["question_text"]
        assert question_message["payload"]["audio_url"] is None
        assert question_message["payload"]["panelist_id"] == session["panelists"][0]["id"]


def test_session_completes_after_question_limit(ws_client, stub_external_services):
    user = _register(ws_client)
    token = user["tokens"]["access_token"]
    session = _create_session(ws_client, token)

    with ws_client.websocket_connect(_stream_url(session["id"], token)) as ws:
        ws.receive_json()  # initial session_state

        for i in range(QUESTION_LIMIT):
            ws.send_json({"type": "user_response", "text": f"Answer {i}", "duration_ms": 1000})
            score_message = ws.receive_json()
            assert score_message["type"] == "score_update"

            question_message = ws.receive_json()
            assert question_message["type"] == "panelist_question"

            if i == QUESTION_LIMIT - 1:
                complete_message = ws.receive_json()
                assert complete_message["type"] == "session_complete"
                assert complete_message["payload"]["question_count"] == QUESTION_LIMIT

        with pytest.raises(WebSocketDisconnect):
            ws.receive_json()

    response = ws_client.get(
        f"/api/v1/sessions/{session['id']}/replay", headers={"Authorization": f"Bearer {token}"}
    )
    assert response.status_code == 200
    body = response.json()["data"]
    assert body["status"] == "completed"
    assert len(body["turns"]) == QUESTION_LIMIT * 2


def test_gesture_log_bundled_into_next_user_response_patches_prior_panelist_turn(
    ws_client, stub_external_services
):
    user = _register(ws_client)
    token = user["tokens"]["access_token"]
    session = _create_session(ws_client, token)
    gestures = [{"t_ms": 120, "gesture": "nod"}, {"t_ms": 800, "gesture": "lean_in"}]

    with ws_client.websocket_connect(_stream_url(session["id"], token)) as ws:
        ws.receive_json()  # initial session_state

        ws.send_json({"type": "user_response", "text": "First answer.", "duration_ms": 2000})
        ws.receive_json()  # score_update
        ws.receive_json()  # panelist_question (sequence 1)

        ws.send_json(
            {
                "type": "user_response",
                "text": "Second answer, having watched the panelist's gestures.",
                "duration_ms": 2000,
                "previous_turn_gestures": gestures,
            }
        )
        ws.receive_json()  # score_update
        ws.receive_json()  # panelist_question (sequence 3)

    end_response = ws_client.post(
        f"/api/v1/sessions/{session['id']}/end", headers={"Authorization": f"Bearer {token}"}
    )
    assert end_response.status_code == 200

    replay = ws_client.get(
        f"/api/v1/sessions/{session['id']}/replay", headers={"Authorization": f"Bearer {token}"}
    )
    turns = replay.json()["data"]["turns"]
    panelist_turn_at_sequence_1 = next(t for t in turns if t["sequence"] == 1)
    assert panelist_turn_at_sequence_1["gesture_sequence"] == gestures


def test_audio_storage_key_is_persisted_for_user_turn(ws_client, stub_external_services):
    user = _register(ws_client)
    token = user["tokens"]["access_token"]
    session = _create_session(ws_client, token)
    storage_key = f"sessions/{session['id']}/turns/0/user-{uuid.uuid4()}"

    with ws_client.websocket_connect(_stream_url(session["id"], token)) as ws:
        ws.receive_json()  # initial session_state
        ws.send_json(
            {
                "type": "user_response",
                "text": "Answer with a recording.",
                "duration_ms": 2500,
                "audio_storage_key": storage_key,
            }
        )
        ws.receive_json()  # score_update
        ws.receive_json()  # panelist_question

    end_response = ws_client.post(
        f"/api/v1/sessions/{session['id']}/end", headers={"Authorization": f"Bearer {token}"}
    )
    assert end_response.status_code == 200

    replay = ws_client.get(
        f"/api/v1/sessions/{session['id']}/replay", headers={"Authorization": f"Bearer {token}"}
    )
    user_turn = next(t for t in replay.json()["data"]["turns"] if t["speaker_type"] == "user")
    assert user_turn["audio_url"] is not None
    assert storage_key in user_turn["audio_url"]


def test_real_time_feedback_disabled_suppresses_score_update(ws_client, stub_external_services):
    user = _register(ws_client)
    token = user["tokens"]["access_token"]
    session = _create_session(ws_client, token, real_time_feedback=False)

    with ws_client.websocket_connect(_stream_url(session["id"], token)) as ws:
        ws.receive_json()  # initial session_state

        ws.send_json({"type": "user_response", "text": "An answer.", "duration_ms": 1000})

        # With real_time_feedback off, the very next message is the question itself —
        # no score_update is ever sent for this connection.
        message = ws.receive_json()
        assert message["type"] == "panelist_question"


def test_real_time_feedback_enabled_sends_score_update(ws_client, stub_external_services):
    user = _register(ws_client)
    token = user["tokens"]["access_token"]
    session = _create_session(ws_client, token, real_time_feedback=True)

    with ws_client.websocket_connect(_stream_url(session["id"], token)) as ws:
        ws.receive_json()  # initial session_state

        ws.send_json({"type": "user_response", "text": "An answer.", "duration_ms": 1000})

        message = ws.receive_json()
        assert message["type"] == "score_update"


def test_answer_timer_enabled_advertises_duration_on_connect_and_each_question(
    ws_client, stub_external_services
):
    user = _register(ws_client)
    token = user["tokens"]["access_token"]
    session = _create_session(ws_client, token, answer_timer=True, real_time_feedback=False)

    with ws_client.websocket_connect(_stream_url(session["id"], token)) as ws:
        initial = ws.receive_json()
        assert initial["payload"]["answer_timer_seconds"] is not None

        ws.send_json({"type": "user_response", "text": "An answer.", "duration_ms": 1000})
        question = ws.receive_json()
        assert question["type"] == "panelist_question"
        assert question["payload"]["answer_timer_seconds"] is not None


def test_answer_timer_disabled_omits_duration(ws_client, stub_external_services):
    user = _register(ws_client)
    token = user["tokens"]["access_token"]
    session = _create_session(ws_client, token, answer_timer=False, real_time_feedback=False)

    with ws_client.websocket_connect(_stream_url(session["id"], token)) as ws:
        initial = ws.receive_json()
        assert initial["payload"]["answer_timer_seconds"] is None

        ws.send_json({"type": "user_response", "text": "An answer.", "duration_ms": 1000})
        question = ws.receive_json()
        assert question["payload"]["answer_timer_seconds"] is None


def test_save_transcript_disabled_persists_no_turns_but_session_still_progresses(
    ws_client, stub_external_services
):
    user = _register(ws_client)
    token = user["tokens"]["access_token"]
    session = _create_session(ws_client, token, save_transcript=False, real_time_feedback=True)

    with ws_client.websocket_connect(_stream_url(session["id"], token)) as ws:
        ws.receive_json()  # initial session_state

        for i in range(QUESTION_LIMIT):
            ws.send_json({"type": "user_response", "text": f"Answer {i}", "duration_ms": 1000})
            score_message = ws.receive_json()
            assert score_message["type"] == "score_update"
            assert score_message["payload"]["question_count"] == i + 1

            question_message = ws.receive_json()
            assert question_message["type"] == "panelist_question"

            if i == QUESTION_LIMIT - 1:
                complete_message = ws.receive_json()
                assert complete_message["type"] == "session_complete"

    # Scores still accumulate on the session row even though no transcript was kept.
    replay = ws_client.get(
        f"/api/v1/sessions/{session['id']}/replay", headers={"Authorization": f"Bearer {token}"}
    )
    body = replay.json()["data"]
    assert body["status"] == "completed"
    assert body["turns"] == []


def test_connect_rejects_invalid_token(ws_client, stub_external_services):
    user = _register(ws_client)
    token = user["tokens"]["access_token"]
    session = _create_session(ws_client, token)

    with pytest.raises(WebSocketDisconnect) as exc_info:
        with ws_client.websocket_connect(_stream_url(session["id"], "not-a-real-token")):
            pass

    assert exc_info.value.code == 4401


def test_connect_rejects_session_belonging_to_another_user(ws_client, stub_external_services):
    owner = _register(ws_client)
    session = _create_session(ws_client, owner["tokens"]["access_token"])

    other = _register(ws_client)

    with pytest.raises(WebSocketDisconnect) as exc_info:
        with ws_client.websocket_connect(_stream_url(session["id"], other["tokens"]["access_token"])):
            pass

    assert exc_info.value.code == 4403


def test_connect_rejects_unknown_session(ws_client, stub_external_services):
    user = _register(ws_client)

    with pytest.raises(WebSocketDisconnect) as exc_info:
        with ws_client.websocket_connect(_stream_url(str(uuid.uuid4()), user["tokens"]["access_token"])):
            pass

    assert exc_info.value.code == 4404


def test_connect_rejects_already_ended_session(ws_client, stub_external_services):
    user = _register(ws_client)
    token = user["tokens"]["access_token"]
    session = _create_session(ws_client, token)

    ws_client.post(f"/api/v1/sessions/{session['id']}/end", headers={"Authorization": f"Bearer {token}"})

    with pytest.raises(WebSocketDisconnect) as exc_info:
        with ws_client.websocket_connect(_stream_url(session["id"], token)):
            pass

    assert exc_info.value.code == 4409
