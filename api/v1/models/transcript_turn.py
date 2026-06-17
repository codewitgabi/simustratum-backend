import uuid
from datetime import datetime
from enum import Enum as PyEnum

from sqlalchemy import Boolean, DateTime, Enum, ForeignKey, Integer, String, UniqueConstraint, func
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from api.database import Base


class SpeakerType(str, PyEnum):
    PANELIST = "panelist"
    USER = "user"


class TranscriptTurn(Base):
    __tablename__ = "transcript_turns"
    __table_args__ = (
        UniqueConstraint("session_id", "sequence", name="uq_transcript_turns_session_sequence"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    session_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("sessions.id", ondelete="CASCADE"), nullable=False, index=True
    )
    sequence: Mapped[int] = mapped_column(Integer, nullable=False)
    speaker_type: Mapped[SpeakerType] = mapped_column(Enum(SpeakerType), nullable=False)
    panelist_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    text: Mapped[str] = mapped_column(String, nullable=False)
    audio_url: Mapped[str | None] = mapped_column(String(500), nullable=True)
    started_at_ms: Mapped[int] = mapped_column(Integer, nullable=False)
    ended_at_ms: Mapped[int] = mapped_column(Integer, nullable=False)
    gesture_sequence: Mapped[list[dict] | None] = mapped_column(JSONB, nullable=True)
    score_snapshot: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    is_followup: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    targets_weakness: Mapped[str | None] = mapped_column(String(255), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
