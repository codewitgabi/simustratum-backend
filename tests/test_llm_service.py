import uuid

from api.v1.models.transcript_turn import SpeakerType, TranscriptTurn
from api.v1.services.llm_service import PanelistPersona, _build_message_history


def _turn(sequence: int, speaker_type: SpeakerType, text: str, panelist_id: str | None) -> TranscriptTurn:
    return TranscriptTurn(
        id=uuid.uuid4(),
        session_id=uuid.uuid4(),
        sequence=sequence,
        speaker_type=speaker_type,
        panelist_id=panelist_id,
        text=text,
        started_at_ms=sequence * 1000,
        ended_at_ms=sequence * 1000 + 500,
    )


def test_build_message_history_maps_roles_for_current_panelist():
    okafor = PanelistPersona(id="p-okafor", name="Dr. Okafor", role="Methods", strictness=75, inquisitiveness=80)
    amara = PanelistPersona(id="p-amara", name="Prof. Amara", role="Theory", strictness=50, inquisitiveness=60)
    bello = PanelistPersona(id="p-bello", name="Dr. Bello", role="Ethics", strictness=40, inquisitiveness=30)
    all_panelists = {p.id: p for p in (okafor, amara, bello)}

    turns = [
        _turn(0, SpeakerType.PANELIST, "Walk us through your methodology.", okafor.id),
        _turn(1, SpeakerType.USER, "I used a mixed-methods approach.", None),
        _turn(2, SpeakerType.PANELIST, "How does that connect to the theoretical framework?", amara.id),
        _turn(3, SpeakerType.USER, "It builds on constructivist theory.", None),
    ]

    messages = _build_message_history(turns, current_panelist_id=okafor.id, all_panelists=all_panelists)

    assert messages == [
        {"role": "assistant", "content": "Walk us through your methodology."},
        {"role": "user", "content": "[Student]: I used a mixed-methods approach."},
        {"role": "user", "content": "[Prof. Amara]: How does that connect to the theoretical framework?"},
        {"role": "user", "content": "[Student]: It builds on constructivist theory."},
    ]


def test_build_message_history_marks_only_current_panelists_questions_as_assistant():
    okafor = PanelistPersona(id="p-okafor", name="Dr. Okafor", role="Methods", strictness=75, inquisitiveness=80)
    amara = PanelistPersona(id="p-amara", name="Prof. Amara", role="Theory", strictness=50, inquisitiveness=60)
    all_panelists = {p.id: p for p in (okafor, amara)}

    turns = [
        _turn(0, SpeakerType.PANELIST, "Opening question from Okafor.", okafor.id),
        _turn(1, SpeakerType.USER, "Answer one.", None),
        _turn(2, SpeakerType.PANELIST, "Opening question from Amara.", amara.id),
    ]

    # Now generating Amara's NEXT question — Amara's own prior turn is 'assistant',
    # Okafor's prior turn becomes 'user' context prefixed with his name.
    messages = _build_message_history(turns, current_panelist_id=amara.id, all_panelists=all_panelists)

    assert messages == [
        {"role": "user", "content": "[Dr. Okafor]: Opening question from Okafor."},
        {"role": "user", "content": "[Student]: Answer one."},
        {"role": "assistant", "content": "Opening question from Amara."},
    ]
