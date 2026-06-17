from typing import Any

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from api.v1.models.session import Session
from api.v1.schemas.session import CreateSessionRequest


async def create_session(
    user_id: Any, body: CreateSessionRequest, db: AsyncSession
) -> Session:
    session = Session(
        user_id=user_id,
        scenario=body.scenario,
        topic=body.topic,
        document_id=body.document_id,
        panelists=[p.model_dump() for p in body.panelists],
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
