import uuid
from datetime import datetime, timezone
from typing import Any

from fastapi import HTTPException, status
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from api.v1.models.session import Session, SessionStatus
from api.v1.schemas.session import CreateSessionRequest
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


async def create_session(
    user_id: Any, body: CreateSessionRequest, db: AsyncSession
) -> Session:
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
