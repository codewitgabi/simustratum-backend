from enum import Enum as PyEnum

from pydantic import BaseModel

from api.v1.models.session import SessionStatus


class WSMessageType(str, PyEnum):
    PANELIST_SPEAKING = "panelist_speaking"
    PANELIST_QUESTION = "panelist_question"
    USER_TURN_START = "user_turn_start"
    USER_TRANSCRIPT_PARTIAL = "user_transcript_partial"
    USER_TURN_END = "user_turn_end"
    SCORE_UPDATE = "score_update"
    SESSION_STATE = "session_state"
    SESSION_COMPLETE = "session_complete"
    ERROR = "error"


class ScoreUpdatePayload(BaseModel):
    clarity: int
    confidence: int
    structure: int
    question_count: int


class PanelistQuestionPayload(BaseModel):
    panelist_id: str
    question_text: str
    is_followup: bool
    audio_url: str | None = None


class SessionStatePayload(BaseModel):
    """Sent on connect/reconnect so the client can resync."""

    status: SessionStatus
    question_count: int
    clarity: int | None
    confidence: int | None
    structure: int | None
    current_panelist_id: str | None
    awaiting_user_response: bool


class ErrorPayload(BaseModel):
    message: str


class SessionCompletePayload(BaseModel):
    clarity: int
    confidence: int
    structure: int
    question_count: int


class UserResponseMessage(BaseModel):
    """Incoming message from the client during the live turn loop."""

    type: str = "user_response"
    text: str
    audio_storage_key: str | None = None
    duration_ms: int
    # Gesture timeline the client just finished animating for the panelist
    # turn it watched before answering — bundled here rather than sent as a
    # separate message, see Part 5 of the audio-replay handout.
    previous_turn_gestures: list[dict] | None = None


class AudioUploadRequest(BaseModel):
    turn_sequence: int
    content_type: str


class AudioUploadResponse(BaseModel):
    upload_url: str
    storage_key: str
    upload_params: dict[str, str]


def ws_envelope(message_type: WSMessageType, payload: BaseModel) -> dict:
    return {"type": message_type.value, "payload": payload.model_dump()}
