from collections import Counter

from api.v1.models.transcript_turn import SpeakerType, TranscriptTurn
from api.v1.services.llm_service import PanelistPersona


def select_next_panelist(
    panelists: list[PanelistPersona],
    turns_so_far: list[TranscriptTurn],
) -> PanelistPersona:
    """Whoever has spoken least gets priority; ties broken by original list order."""
    speak_counts = Counter(
        t.panelist_id for t in turns_so_far if t.speaker_type == SpeakerType.PANELIST
    )
    return min(panelists, key=lambda p: (speak_counts.get(p.id, 0), panelists.index(p)))
