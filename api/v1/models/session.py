import uuid
from datetime import datetime
from enum import Enum as PyEnum

from sqlalchemy import Boolean, DateTime, Enum, ForeignKey, Integer, String, func
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from api.database import Base


class ScenarioType(str, PyEnum):
    TUTORIAL_PRACTICE = "tutorial_practice"
    PRESENTATION = "presentation"
    PROJECT_DEFENSE = "project_defense"
    ORAL_EXAMINATION = "oral_examination"
    SEMINAR_DEFENSE = "seminar_defense"
    ENGLISH_PROFICIENCY = "english_proficiency"


class Session(Base):
    __tablename__ = "sessions"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    scenario: Mapped[ScenarioType] = mapped_column(Enum(ScenarioType), nullable=False)
    topic: Mapped[str] = mapped_column(String(500), nullable=False)
    document_id: Mapped[str | None] = mapped_column(String(255), nullable=True)
    panelists: Mapped[list[dict]] = mapped_column(JSONB, nullable=False, default=list)
    real_time_feedback: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    answer_timer: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    save_transcript: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    clarity: Mapped[int | None] = mapped_column(Integer, nullable=True)
    confidence: Mapped[int | None] = mapped_column(Integer, nullable=True)
    structure: Mapped[int | None] = mapped_column(Integer, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )
