import uuid
from enum import Enum as PyEnum

from fastapi import WebSocket

from api.v1.services.llm_service import PanelistPersona

QUESTION_LIMIT = 6
DEFAULT_SCORE_BASELINE = 50


class TurnState(str, PyEnum):
    WAITING_TO_START = "waiting_to_start"
    PANELIST_SPEAKING = "panelist_speaking"
    USER_TURN = "user_turn"
    PROCESSING_RESPONSE = "processing_response"
    COMPLETE = "complete"


class SessionOrchestrator:
    """
    Per-connection live-session state. One instance per active WebSocket connection,
    registered in the module-level registry below so the REST end-session endpoint
    can signal it to close without needing to share a process-wide singleton.
    """

    def __init__(
        self,
        session_id: uuid.UUID,
        websocket: WebSocket,
        panelists: list[PanelistPersona],
        clarity: int | None,
        confidence: int | None,
        structure: int | None,
        question_count: int,
    ) -> None:
        self.session_id = session_id
        self.websocket = websocket
        self.panelists = panelists
        self.turn_state = TurnState.WAITING_TO_START
        self.current_panelist_id: str | None = None
        self.clarity = clarity if clarity is not None else DEFAULT_SCORE_BASELINE
        self.confidence = confidence if confidence is not None else DEFAULT_SCORE_BASELINE
        self.structure = structure if structure is not None else DEFAULT_SCORE_BASELINE
        self.question_count = question_count

    @property
    def awaiting_user_response(self) -> bool:
        return self.turn_state == TurnState.USER_TURN

    async def request_close(self, code: int = 1000, reason: str = "Session ended") -> None:
        """Called by the REST end-session endpoint to gracefully stop a live socket."""
        self.turn_state = TurnState.COMPLETE
        try:
            await self.websocket.close(code=code, reason=reason)
        except RuntimeError:
            # socket already closed/closing
            pass


_registry: dict[uuid.UUID, SessionOrchestrator] = {}


def register_orchestrator(orchestrator: SessionOrchestrator) -> None:
    _registry[orchestrator.session_id] = orchestrator


def unregister_orchestrator(session_id: uuid.UUID) -> None:
    _registry.pop(session_id, None)


def get_orchestrator(session_id: uuid.UUID) -> SessionOrchestrator | None:
    return _registry.get(session_id)
