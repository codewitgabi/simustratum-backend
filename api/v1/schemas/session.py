import uuid
from datetime import datetime

from pydantic import BaseModel, Field

from api.v1.models.session import ScenarioType


class PanelistRequest(BaseModel):
    name: str
    role: str | None = None
    strictness: int = Field(ge=0, le=100)
    inquisitiveness: int = Field(ge=0, le=100)


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
    panelists: list[PanelistRequest]
    real_time_feedback: bool
    answer_timer: bool
    save_transcript: bool
    clarity: int | None
    confidence: int | None
    structure: int | None
    created_at: datetime

    model_config = {"from_attributes": True}


class SessionListItem(BaseModel):
    id: uuid.UUID
    title: str
    scenario: ScenarioType
    score: int
    created_at: datetime

    model_config = {"from_attributes": True}
