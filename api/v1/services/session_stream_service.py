import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from api.v1.models.session import Session
from api.v1.models.transcript_turn import TranscriptTurn
from api.v1.schemas.transcript_turn import SessionStatePayload
from api.v1.services.llm_service import PanelistPersona
from api.v1.services.session_orchestrator import ANSWER_TIMER_SECONDS, SessionOrchestrator


def build_personas(panelists_data: list[dict]) -> list[PanelistPersona]:
    return [PanelistPersona(**p) for p in panelists_data]


async def get_session(db: AsyncSession, session_id: uuid.UUID) -> Session | None:
    result = await db.execute(select(Session).where(Session.id == session_id))
    return result.scalar_one_or_none()


async def get_turns(db: AsyncSession, session_id: uuid.UUID) -> list[TranscriptTurn]:
    result = await db.execute(
        select(TranscriptTurn)
        .where(TranscriptTurn.session_id == session_id)
        .order_by(TranscriptTurn.sequence)
    )
    return list(result.scalars().all())


async def load_turns(
    db: AsyncSession, session_id: uuid.UUID, orchestrator: SessionOrchestrator
) -> list[TranscriptTurn]:
    """save_transcript=False means nothing is ever written to transcript_turns, so the
    only history available is the in-memory list kept on the orchestrator for the
    lifetime of this connection."""
    if orchestrator.save_transcript:
        return await get_turns(db, session_id)
    return orchestrator.transcript_turns


async def add_turn(db: AsyncSession, orchestrator: SessionOrchestrator, turn: TranscriptTurn) -> None:
    if orchestrator.save_transcript:
        db.add(turn)
        await db.commit()
    else:
        orchestrator.transcript_turns.append(turn)


def build_session_state_payload(
    session: Session, orchestrator: SessionOrchestrator, current_panelist_id: str | None
) -> SessionStatePayload:
    return SessionStatePayload(
        status=session.status,
        question_count=orchestrator.question_count,
        clarity=orchestrator.clarity,
        confidence=orchestrator.confidence,
        structure=orchestrator.structure,
        current_panelist_id=current_panelist_id,
        awaiting_user_response=orchestrator.awaiting_user_response,
        answer_timer_seconds=ANSWER_TIMER_SECONDS if orchestrator.answer_timer else None,
    )
