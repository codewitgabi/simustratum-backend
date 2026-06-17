import random

from api.v1.models.session import ScenarioType


async def score_response(
    user_text: str,
    scenario: ScenarioType,
    topic: str,
) -> dict:
    """
    Placeholder. Returns plausible incremental deltas for clarity/confidence/structure.
    Replace with a real scoring implementation later (likely also an Anthropic call
    with a structured rubric output, or a separate fine-tuned approach) — this
    function's signature should not need to change when that happens.
    """
    return {
        "clarity": random.randint(-2, 6),
        "confidence": random.randint(-2, 6),
        "structure": random.randint(-2, 6),
    }
