"""Shared helpers for integration tests — all go through the real HTTP API,
never the service layer directly, so they exercise the same code path a real
client would."""

import uuid
from typing import Any

from httpx import AsyncClient

DEFAULT_PASSWORD = "correct-password-123"


async def register_user(
    client: AsyncClient, email: str, password: str = DEFAULT_PASSWORD, full_name: str = "Test User"
) -> dict[str, Any]:
    response = await client.post(
        "/api/v1/auth/register",
        json={"full_name": full_name, "email": email, "password": password},
    )
    assert response.status_code == 201, response.text
    return response.json()["data"]


def auth_header(access_token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {access_token}"}


async def registered_user_headers(client: AsyncClient, email: str | None = None) -> dict[str, str]:
    email = email or f"user-{uuid.uuid4().hex[:12]}@example.com"
    data = await register_user(client, email)
    return auth_header(data["tokens"]["access_token"])


def sample_panelists() -> list[dict[str, Any]]:
    return [
        {"name": "Dr. Okafor", "role": "Methods", "strictness": 70, "inquisitiveness": 60},
        {"name": "Prof. Diallo", "role": "Theory", "strictness": 40, "inquisitiveness": 50},
    ]


async def set_session_status(session_id: str, status_value: str) -> None:
    """
    Test-only seam: flips a session's status directly in the DB. Reaching
    IN_PROGRESS for real means driving the WebSocket turn loop, which is exercised
    on its own in tests/session_stream — REST endpoints that merely *require*
    IN_PROGRESS as a precondition shouldn't need to stand up a socket just to get
    there. This writes through the same DB the app itself is configured to use.
    """
    import api.database as database_module
    from api.v1.models.session import Session, SessionStatus

    async with database_module.AsyncSessionLocal() as db:
        session = await db.get(Session, uuid.UUID(session_id))
        session.status = SessionStatus(status_value)
        await db.commit()


async def insert_transcript_turn(session_id: str, **overrides: Any) -> dict[str, Any]:
    """
    Seeds a TranscriptTurn row directly — used by replay tests, which exercise a
    *read* of finished-session history rather than the live turn-by-turn flow (that
    flow is covered end-to-end by tests/session_stream instead).
    """
    import api.database as database_module
    from api.v1.models.transcript_turn import SpeakerType, TranscriptTurn

    defaults: dict[str, Any] = {
        "sequence": 0,
        "speaker_type": SpeakerType.PANELIST,
        "panelist_id": None,
        "text": "Default turn text",
        "audio_storage_key": None,
        "started_at_ms": 0,
        "ended_at_ms": 0,
        "gesture_sequence": None,
        "score_snapshot": None,
        "is_followup": False,
        "targets_weakness": None,
    }
    defaults.update(overrides)

    async with database_module.AsyncSessionLocal() as db:
        turn = TranscriptTurn(session_id=uuid.UUID(session_id), **defaults)
        db.add(turn)
        await db.commit()
        return defaults


async def create_session_via_api(
    client: AsyncClient,
    headers: dict[str, str],
    *,
    scenario: str = "project_defense",
    topic: str = "A study on distributed consensus",
    document_id: str | None = None,
    panelists: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    body: dict[str, Any] = {
        "scenario": scenario,
        "topic": topic,
        "panelists": panelists if panelists is not None else sample_panelists(),
    }
    if document_id is not None:
        body["document_id"] = document_id

    response = await client.post("/api/v1/sessions", json=body, headers=headers)
    assert response.status_code == 201, response.text
    return response.json()["data"]
