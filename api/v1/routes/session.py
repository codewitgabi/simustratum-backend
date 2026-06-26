import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Query, status
from fastapi.encoders import jsonable_encoder
from fastapi.responses import JSONResponse
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from api.database import get_db, get_read_db
from api.response import success_response
from api.v1.dependencies.auth import get_current_user
from api.v1.models.session import Session, SessionStatus
from api.v1.models.user import User
from api.v1.schemas.session import (
    CreateSessionRequest,
    ReplaySessionResponse,
    SessionEndRequest,
    SessionEndResponse,
    SessionListItem,
    SessionResponse,
)
from api.v1.schemas.transcript_turn import AudioUploadRequest, AudioUploadResponse
from api.v1.services import billing_service, session as session_service

session_router = APIRouter(prefix="/sessions", tags=["Sessions"])


@session_router.post("", status_code=status.HTTP_201_CREATED)
async def create_session(
    body: CreateSessionRequest,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> JSONResponse:
    await billing_service.check_session_limit(user, db)

    session = await session_service.create_session(user.id, body, db)

    await billing_service.increment_session_usage(user, db)

    return success_response(
        message="Session created successfully",
        status_code=status.HTTP_201_CREATED,
        data=SessionResponse.model_validate(session).model_dump(),
    )


@session_router.get("", status_code=status.HTTP_200_OK)
async def list_sessions(
    page: int = Query(default=1, ge=1),
    limit: int = Query(default=20, ge=1, le=100),
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_read_db),
) -> JSONResponse:
    sessions, total = await session_service.list_sessions(user.id, page, limit, db)
    items = [
        SessionListItem(
            id=s.id,
            title=s.topic,
            scenario=s.scenario,
            status=s.status,
            score=session_service.compute_overall_score(s),
            created_at=s.created_at,
        ).model_dump()
        for s in sessions
    ]
    return success_response(
        message="Sessions retrieved successfully",
        data={
            "items": items,
            "meta": {"total": total, "page": page, "limit": limit},
        },
    )


@session_router.post("/{session_id}/start", status_code=status.HTTP_200_OK)
async def start_session(
    session_id: uuid.UUID,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> JSONResponse:
    result = await db.execute(select(Session).where(Session.id == session_id))
    session = result.scalar_one_or_none()

    if session is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Session not found")
    if session.user_id != user.id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Forbidden")
    if session.status in (SessionStatus.COMPLETED, SessionStatus.ABANDONED):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Session already ended",
        )

    if user.plan != "pro" and len(session.panelists or []) > 1:
        return JSONResponse(
            status_code=status.HTTP_403_FORBIDDEN,
            content=jsonable_encoder({
                "success": False,
                "message": "Free accounts support 1 AI panelist per session. Upgrade to Student Pro for up to 3.",
                "error_code": "panelist_limit_exceeded",
            }),
        )

    if session.status == SessionStatus.PENDING:
        session.status = SessionStatus.IN_PROGRESS
        session.started_at = datetime.now(timezone.utc)
        await db.commit()

    return success_response(
        message="Session started",
        data={"status": session.status.value},
    )


@session_router.post("/{session_id}/end", status_code=status.HTTP_200_OK)
async def end_session(
    session_id: uuid.UUID,
    body: SessionEndRequest = SessionEndRequest(),
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> JSONResponse:
    session = await session_service.end_session(user.id, session_id, body.reason, db)

    duration_seconds = None
    if session.started_at is not None and session.ended_at is not None:
        duration_seconds = int((session.ended_at - session.started_at).total_seconds())

    response = SessionEndResponse(
        id=session.id,
        status=session.status,
        clarity=session.clarity,
        confidence=session.confidence,
        structure=session.structure,
        question_count=session.question_count,
        started_at=session.started_at,
        ended_at=session.ended_at,
        duration_seconds=duration_seconds,
    )
    return success_response(message="Session ended successfully", data=response.model_dump())


@session_router.delete("/{session_id}", status_code=status.HTTP_200_OK)
async def delete_session(
    session_id: uuid.UUID,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> JSONResponse:
    await session_service.delete_session(user.id, session_id, db)
    return success_response(message="Session deleted successfully", data=None)


@session_router.post("/{session_id}/turns/audio-upload-url", status_code=status.HTTP_200_OK)
async def request_audio_upload_url(
    session_id: uuid.UUID,
    body: AudioUploadRequest,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> JSONResponse:
    response = await session_service.create_audio_upload_url(user.id, session_id, body, db)
    return success_response(message="Upload URL generated successfully", data=response.model_dump())


@session_router.get("/{session_id}/replay", status_code=status.HTTP_200_OK)
async def get_session_replay(
    session_id: uuid.UUID,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_read_db),
) -> JSONResponse:
    response: ReplaySessionResponse = await session_service.get_session_replay(user.id, session_id, db)
    return success_response(message="Session replay retrieved successfully", data=response.model_dump())
