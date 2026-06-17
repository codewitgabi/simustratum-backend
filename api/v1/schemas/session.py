import uuid
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field

from api.v1.models.session import ScenarioType, SessionStatus


class PanelistRequest(BaseModel):
    name: str
    role: str | None = None
    strictness: int = Field(ge=0, le=100)
    inquisitiveness: int = Field(ge=0, le=100)


class PanelistResponse(PanelistRequest):
    id: str


class CreateSessionRequest(BaseModel):
    scenario: ScenarioType
    topic: str
    document_id: str | None = None
    panelists: list[PanelistRequest] = Field(min_length=1)
    real_time_feedback: bool = False
    answer_timer: bool = False
    save_transcript: bool = False


class SessionResponse(BaseModel):
    id: uuid.UUID
    scenario: ScenarioType
    topic: str
    document_id: str | None
    panelists: list[PanelistResponse]
    real_time_feedback: bool
    answer_timer: bool
    save_transcript: bool
    status: SessionStatus
    question_count: int
    clarity: int | None
    confidence: int | None
    structure: int | None
    created_at: datetime

    model_config = {"from_attributes": True}


class SessionStartResponse(BaseModel):
    id: uuid.UUID
    status: SessionStatus
    started_at: datetime
    question_count: int

    model_config = {"from_attributes": True}


class SessionEndRequest(BaseModel):
    reason: Literal["completed", "user_abandoned", "error"] = "completed"


class SessionEndResponse(BaseModel):
    id: uuid.UUID
    status: SessionStatus
    clarity: int | None
    confidence: int | None
    structure: int | None
    question_count: int
    started_at: datetime | None
    ended_at: datetime | None
    duration_seconds: int | None

    model_config = {"from_attributes": True}


class SessionListItem(BaseModel):
    id: uuid.UUID
    title: str
    scenario: ScenarioType
    score: int
    created_at: datetime

    model_config = {"from_attributes": True}
