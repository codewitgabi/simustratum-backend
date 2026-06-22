import asyncio
import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, Query, WebSocket, WebSocketDisconnect
from sqlalchemy.ext.asyncio import AsyncSession

from api.database import get_db
from api.v1.dependencies.auth import get_current_user_ws
from api.v1.models.session import SessionStatus
from api.v1.models.transcript_turn import SpeakerType, TranscriptTurn
from api.v1.schemas.transcript_turn import (
    ErrorPayload,
    PanelistQuestionPayload,
    ScoreUpdatePayload,
    SessionCompletePayload,
    UserResponseMessage,
    WSMessageType,
    ws_envelope,
)
from api.v1.services.anthropic_client import get_anthropic_client
from api.v1.services.document_service import retrieve_relevant_chunks
from api.v1.services.gemini_client import get_gemini_client
from api.v1.services.llm_service import generate_next_question
from api.v1.services.panelist_selector import select_next_panelist
from api.v1.services.scoring_service import score_response
from api.v1.services.session_orchestrator import (
    ANSWER_TIMER_SECONDS,
    QUESTION_LIMIT,
    SessionOrchestrator,
    TurnState,
    register_orchestrator,
    unregister_orchestrator,
)
from api.v1.services.session_stream_service import (
    add_turn,
    build_personas,
    build_session_state_payload,
    get_session,
    load_turns,
)
from api.v1.utils.logger import get_logger

logger = get_logger("session_stream")

stream_router = APIRouter(tags=["Sessions"])


@stream_router.websocket("/sessions/{session_id}/stream")
async def session_stream(
    websocket: WebSocket,
    session_id: uuid.UUID,
    token: str = Query(...),
    db: AsyncSession = Depends(get_db),
) -> None:
    # Accept first, then validate — a close() sent before accept() never
    # completes the WebSocket opening handshake, so a real browser can't see
    # the close code or reason at all (the WebSocket spec collapses any
    # pre-handshake failure to code 1006 with no reason, to avoid leaking
    # info cross-origin). Accepting first means rejections below are real,
    # observable closes with the actual code/reason.
    await websocket.accept()

    async def reject(code: int, message: str) -> None:
        await websocket.send_json(ws_envelope(WSMessageType.ERROR, ErrorPayload(message=message)))
        await websocket.close(code=code, reason=message)

    user = await get_current_user_ws(token, db)
    if user is None:
        await reject(4401, "Invalid or expired token")
        return

    session = await get_session(db, session_id)
    if session is None:
        await reject(4404, "Session not found")
        return

    if session.user_id != user.id:
        await reject(4403, "Forbidden")
        return

    if session.status in (SessionStatus.COMPLETED, SessionStatus.ABANDONED):
        await reject(4409, "Session already ended")
        return

    panelists = build_personas(session.panelists)
    panelists_by_id = {p.id: p for p in panelists}

    orchestrator = SessionOrchestrator(
        session_id=session.id,
        websocket=websocket,
        panelists=panelists,
        clarity=session.clarity,
        confidence=session.confidence,
        structure=session.structure,
        question_count=session.question_count,
        real_time_feedback=session.real_time_feedback,
        answer_timer=session.answer_timer,
        save_transcript=session.save_transcript,
    )
    register_orchestrator(orchestrator)

    try:
        if session.status == SessionStatus.PENDING:
            session.status = SessionStatus.IN_PROGRESS
            session.started_at = datetime.now(timezone.utc)
            await db.commit()

            orchestrator.turn_state = TurnState.USER_TURN
            await websocket.send_json(
                ws_envelope(
                    WSMessageType.SESSION_STATE,
                    build_session_state_payload(session, orchestrator, current_panelist_id=None),
                )
            )
        else:
            # Reconnect resync: rebuild visual state from the last persisted turn.
            # (When save_transcript is off, the in-memory history doesn't survive a
            # reconnect — a new orchestrator is created per connection — so this can
            # only resync to "awaiting a response".)
            turns = await load_turns(db, session_id, orchestrator)
            last_turn = turns[-1] if turns else None
            current_panelist_id: str | None = None

            if last_turn is not None and last_turn.speaker_type == SpeakerType.PANELIST:
                current_panelist_id = last_turn.panelist_id
                orchestrator.turn_state = TurnState.USER_TURN
            else:
                orchestrator.turn_state = TurnState.PROCESSING_RESPONSE

            orchestrator.current_panelist_id = current_panelist_id
            await websocket.send_json(
                ws_envelope(
                    WSMessageType.SESSION_STATE,
                    build_session_state_payload(session, orchestrator, current_panelist_id),
                )
            )

        while True:
            raw = await websocket.receive_json()
            if raw.get("type") != "user_response":
                continue

            message = UserResponseMessage.model_validate(raw)
            orchestrator.turn_state = TurnState.PROCESSING_RESPONSE

            turns = await load_turns(db, session_id, orchestrator)
            next_sequence = len(turns)

            # Patch the gesture timeline onto the panelist turn the user just
            # watched, bundled into this message rather than sent separately
            # — see Part 5 of the audio-replay handout for why.
            if message.previous_turn_gestures is not None and turns:
                last_turn = turns[-1]
                if last_turn.speaker_type == SpeakerType.PANELIST:
                    last_turn.gesture_sequence = message.previous_turn_gestures

            user_turn = TranscriptTurn(
                session_id=session_id,
                sequence=next_sequence,
                speaker_type=SpeakerType.USER,
                panelist_id=None,
                text=message.text,
                audio_storage_key=message.audio_storage_key,
                started_at_ms=0,
                ended_at_ms=message.duration_ms,
            )
            await add_turn(db, orchestrator, user_turn)

            turns = await load_turns(db, session_id, orchestrator)
            next_panelist = select_next_panelist(panelists, turns)

            document_context = None
            if session.document_id:
                document_context = await retrieve_relevant_chunks(
                    uuid.UUID(session.document_id), message.text
                )

            try:
                score_delta, next_question = await asyncio.gather(
                    score_response(message.text, session.scenario, session.topic),
                    generate_next_question(
                        next_panelist,
                        session.scenario,
                        session.topic,
                        turns,
                        panelists_by_id,
                        get_gemini_client(),
                        get_anthropic_client(),
                        document_context,
                    ),
                )
                next_question_text = next_question.question_text
                is_followup = next_question.is_followup
                targets_weakness = next_question.targets_weakness
            except Exception:
                logger.exception(
                    "LLM/scoring call failed during live session turn",
                    extra={"session_id": str(session_id)},
                )
                await websocket.send_json(
                    ws_envelope(
                        WSMessageType.ERROR,
                        ErrorPayload(message="Something went wrong generating the next question."),
                    )
                )
                score_delta = {"clarity": 0, "confidence": 0, "structure": 0}
                next_question_text = "Can you expand further on that point?"
                is_followup = False
                targets_weakness = None

            orchestrator.clarity = max(0, min(100, orchestrator.clarity + score_delta["clarity"]))
            orchestrator.confidence = max(0, min(100, orchestrator.confidence + score_delta["confidence"]))
            orchestrator.structure = max(0, min(100, orchestrator.structure + score_delta["structure"]))
            orchestrator.question_count += 1

            session.clarity = orchestrator.clarity
            session.confidence = orchestrator.confidence
            session.structure = orchestrator.structure
            session.question_count = orchestrator.question_count
            await db.commit()

            if orchestrator.real_time_feedback:
                await websocket.send_json(
                    ws_envelope(
                        WSMessageType.SCORE_UPDATE,
                        ScoreUpdatePayload(
                            clarity=orchestrator.clarity,
                            confidence=orchestrator.confidence,
                            structure=orchestrator.structure,
                            question_count=orchestrator.question_count,
                        ),
                    )
                )

            panelist_turn = TranscriptTurn(
                session_id=session_id,
                sequence=next_sequence + 1,
                speaker_type=SpeakerType.PANELIST,
                panelist_id=next_panelist.id,
                text=next_question_text,
                audio_url=None,
                started_at_ms=user_turn.ended_at_ms,
                ended_at_ms=user_turn.ended_at_ms,
                is_followup=is_followup,
                targets_weakness=targets_weakness,
                score_snapshot={
                    "clarity": orchestrator.clarity,
                    "confidence": orchestrator.confidence,
                    "structure": orchestrator.structure,
                },
            )
            await add_turn(db, orchestrator, panelist_turn)

            orchestrator.current_panelist_id = next_panelist.id

            await websocket.send_json(
                ws_envelope(
                    WSMessageType.PANELIST_QUESTION,
                    PanelistQuestionPayload(
                        panelist_id=next_panelist.id,
                        question_text=next_question_text,
                        is_followup=is_followup,
                        audio_url=None,
                        answer_timer_seconds=ANSWER_TIMER_SECONDS if orchestrator.answer_timer else None,
                    ),
                )
            )

            if orchestrator.question_count >= QUESTION_LIMIT:
                orchestrator.turn_state = TurnState.COMPLETE
                session.status = SessionStatus.COMPLETED
                session.ended_at = datetime.now(timezone.utc)
                await db.commit()

                await websocket.send_json(
                    ws_envelope(
                        WSMessageType.SESSION_COMPLETE,
                        SessionCompletePayload(
                            clarity=orchestrator.clarity,
                            confidence=orchestrator.confidence,
                            structure=orchestrator.structure,
                            question_count=orchestrator.question_count,
                        ),
                    )
                )
                await websocket.close(code=1000, reason="Session complete")
                break

            orchestrator.turn_state = TurnState.USER_TURN

    except WebSocketDisconnect:
        logger.info("Session stream disconnected", extra={"session_id": str(session_id)})
        # status stays IN_PROGRESS — the client may reconnect; explicit abandonment
        # only happens via POST /sessions/{id}/end.
    except Exception:
        logger.exception("Unhandled error in session stream loop", extra={"session_id": str(session_id)})
        try:
            await websocket.send_json(
                ws_envelope(WSMessageType.ERROR, ErrorPayload(message="An unexpected error occurred."))
            )
        except Exception:
            pass
    finally:
        unregister_orchestrator(session_id)
