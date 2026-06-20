import uuid
from datetime import datetime, timezone
from typing import Any

from fastapi import HTTPException, status
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from api.v1.models.document import DocumentStatus
from api.v1.models.session import Session, SessionStatus
from api.v1.models.transcript_turn import SpeakerType, TranscriptTurn
from api.v1.schemas.session import CreateSessionRequest, ReplaySessionResponse, ReplayTurn
from api.v1.schemas.transcript_turn import AudioUploadRequest, AudioUploadResponse
from api.v1.services.cloudinary_client import (
    build_audio_storage_key,
    generate_audio_upload_params,
    get_audio_upload_url,
    get_playable_audio_url,
    is_allowed_audio_content_type,
)
from api.v1.services.document_service import get_owned_document
from api.v1.services.session_orchestrator import get_orchestrator


def compute_overall_score(session: Session) -> int:
    components = [c for c in (session.clarity, session.confidence, session.structure) if c is not None]
    if not components:
        return 0
    return round(sum(components) / len(components))


def _build_panelist_dicts(body: CreateSessionRequest) -> list[dict]:
    panelists = []
    for p in body.panelists:
        data = p.model_dump()
        data["id"] = str(uuid.uuid4())
        panelists.append(data)
    return panelists


async def _validate_document(user_id: Any, document_id: str, db: AsyncSession) -> None:
    try:
        parsed_id = uuid.UUID(document_id)
    except ValueError:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid document_id")

    document = await get_owned_document(user_id, parsed_id, db)
    if document is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Document not found")
    if document.status != DocumentStatus.READY:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Document is not ready yet (status: {document.status.value})",
        )


async def create_session(
    user_id: Any, body: CreateSessionRequest, db: AsyncSession
) -> Session:
    if body.document_id is not None:
        await _validate_document(user_id, body.document_id, db)

    session = Session(
        user_id=user_id,
        scenario=body.scenario,
        topic=body.topic,
        document_id=body.document_id,
        panelists=_build_panelist_dicts(body),
        real_time_feedback=body.real_time_feedback,
        answer_timer=body.answer_timer,
        save_transcript=body.save_transcript,
    )
    db.add(session)
    await db.commit()
    await db.refresh(session)
    return session


async def list_sessions(
    user_id: Any, page: int, limit: int, db: AsyncSession
) -> tuple[list[Session], int]:
    total_result = await db.execute(
        select(func.count()).select_from(Session).where(Session.user_id == user_id)
    )
    total = total_result.scalar_one()

    result = await db.execute(
        select(Session)
        .where(Session.user_id == user_id)
        .order_by(Session.created_at.desc())
        .offset((page - 1) * limit)
        .limit(limit)
    )
    sessions = list(result.scalars().all())
    return sessions, total


async def end_session(
    user_id: Any, session_id: uuid.UUID, reason: str, db: AsyncSession
) -> Session:
    result = await db.execute(select(Session).where(Session.id == session_id))
    session = result.scalar_one_or_none()

    if session is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Session not found")
    if session.user_id != user_id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Forbidden")

    if session.status in (SessionStatus.COMPLETED, SessionStatus.ABANDONED):
        return session

    session.status = SessionStatus.COMPLETED if reason == "completed" else SessionStatus.ABANDONED
    if session.ended_at is None:
        session.ended_at = datetime.now(timezone.utc)

    await db.commit()
    await db.refresh(session)

    orchestrator = get_orchestrator(session_id)
    if orchestrator is not None:
        await orchestrator.request_close(reason="Session ended via REST endpoint")

    return session


async def delete_session(user_id: Any, session_id: uuid.UUID, db: AsyncSession) -> None:
    result = await db.execute(select(Session).where(Session.id == session_id))
    session = result.scalar_one_or_none()

    if session is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Session not found")
    if session.user_id != user_id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Forbidden")

    if session.status == SessionStatus.IN_PROGRESS:
        orchestrator = get_orchestrator(session_id)
        if orchestrator is not None:
            await orchestrator.request_close(reason="Session deleted via REST endpoint")

    await db.delete(session)
    await db.commit()


async def create_audio_upload_url(
    user_id: Any, session_id: uuid.UUID, body: AudioUploadRequest, db: AsyncSession
) -> AudioUploadResponse:
    if not is_allowed_audio_content_type(body.content_type):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Unsupported audio content type: {body.content_type}",
        )

    result = await db.execute(select(Session).where(Session.id == session_id))
    session = result.scalar_one_or_none()

    if session is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Session not found")
    if session.user_id != user_id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Forbidden")
    if session.status != SessionStatus.IN_PROGRESS:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Session is not in progress (status: {session.status.value})",
        )

    storage_key = build_audio_storage_key(session_id, body.turn_sequence)
    return AudioUploadResponse(
        upload_url=get_audio_upload_url(),
        storage_key=storage_key,
        upload_params=generate_audio_upload_params(storage_key),
    )


async def get_session_replay(
    user_id: Any, session_id: uuid.UUID, db: AsyncSession
) -> ReplaySessionResponse:
    result = await db.execute(select(Session).where(Session.id == session_id))
    session = result.scalar_one_or_none()

    if session is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Session not found")
    if session.user_id != user_id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Forbidden")
    if session.status in (SessionStatus.PENDING, SessionStatus.IN_PROGRESS):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Session is not finished — use the live WebSocket for an ongoing session",
        )

    turns_result = await db.execute(
        select(TranscriptTurn)
        .where(TranscriptTurn.session_id == session_id)
        .order_by(TranscriptTurn.sequence)
    )
    turns = list(turns_result.scalars().all())

    replay_turns = []
    for turn in turns:
        audio_url = None
        if turn.speaker_type == SpeakerType.USER and turn.audio_storage_key:
            audio_url = get_playable_audio_url(turn.audio_storage_key)

        replay_turns.append(
            ReplayTurn(
                sequence=turn.sequence,
                speaker_type=turn.speaker_type,
                panelist_id=turn.panelist_id,
                text=turn.text,
                audio_url=audio_url,
                started_at_ms=turn.started_at_ms,
                ended_at_ms=turn.ended_at_ms,
                gesture_sequence=turn.gesture_sequence,
                score_snapshot=turn.score_snapshot,
                is_followup=turn.is_followup,
                targets_weakness=turn.targets_weakness,
            )
        )

    return ReplaySessionResponse(
        session_id=session.id,
        scenario=session.scenario,
        topic=session.topic,
        panelists=session.panelists,
        status=session.status,
        started_at=session.started_at,
        ended_at=session.ended_at,
        final_clarity=session.clarity,
        final_confidence=session.confidence,
        final_structure=session.structure,
        turns=replay_turns,
    )
