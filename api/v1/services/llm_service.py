from anthropic import AsyncAnthropic
from google import genai
from google.genai import errors as genai_errors
from google.genai import types as genai_types
from pydantic import BaseModel, Field

from api.v1.models.session import ScenarioType
from api.v1.models.transcript_turn import SpeakerType, TranscriptTurn
from api.v1.utils.logger import get_logger

logger = get_logger("llm_service")

ANTHROPIC_MODEL = "claude-sonnet-4-6"
GEMINI_MODEL = "gemini-2.5-flash"


class PanelistPersona(BaseModel):
    """Built from one entry in Session.panelists (the JSONB list)."""

    id: str
    name: str
    role: str | None = None
    strictness: int
    inquisitiveness: int


class NextQuestion(BaseModel):
    """Forced structured output from the LLM for every panelist turn."""

    question_text: str = Field(description="The single question to ask the student, in character.")
    is_followup: bool = Field(
        description="True if this question directly probes the student's previous answer rather than opening a new line of questioning."
    )
    targets_weakness: str | None = Field(
        default=None,
        description=(
            "A short phrase naming the specific weak point being probed, if any "
            "(e.g. 'sample size justification'). Null if this is a general/opening question."
        ),
    )


NEXT_QUESTION_TOOL = {
    "name": "ask_question",
    "description": "Submit the next question to ask the student.",
    "input_schema": {
        "type": "object",
        "properties": {
            "question_text": {"type": "string"},
            "is_followup": {"type": "boolean"},
            "targets_weakness": {"type": ["string", "null"]},
        },
        "required": ["question_text", "is_followup"],
    },
}


def build_system_prompt(
    persona: PanelistPersona,
    scenario: ScenarioType,
    topic: str,
    document_context: list[str] | None = None,
) -> str:
    if persona.strictness > 65:
        tone = "demanding and skeptical — you push back on vague or unsupported claims"
    elif persona.strictness < 35:
        tone = (
            "supportive but thorough — you give the student room to explain, "
            "while still expecting rigor"
        )
    else:
        tone = "professionally neutral and measured"

    if persona.inquisitiveness > 65:
        depth = (
            "You actively probe weak points and ask sharp follow-up questions "
            "when an answer seems incomplete or under-justified."
        )
    else:
        depth = "You ask clearly-scoped, mostly independent questions rather than deep follow-up chains."

    scenario_label = scenario.value.replace("_", " ")
    role_label = persona.role or "the subject matter"

    document_block = ""
    if document_context:
        excerpts = "\n\n".join(f"[Excerpt {i + 1}]\n{chunk}" for i, chunk in enumerate(document_context))
        document_block = f"""

The student has submitted the following document for this session (e.g. their paper,
slides, or proposal). Base your questions primarily on its actual content — ask about
specifics, claims, and details from these excerpts rather than relying on general
knowledge of the topic. Only fall back to general knowledge if the excerpts genuinely
don't cover something directly relevant to what you want to ask.

{excerpts}"""

    return f"""You are {persona.name}, a panelist in a {scenario_label} session.
Your area of expertise is {role_label}. Your questioning style is {tone}. {depth}

The student's topic is: "{topic}"{document_block}

You will be shown the conversation so far, in order. Ask exactly ONE question, fully
in character as {persona.name}. Build naturally on what has already been discussed —
do not repeat a question that has already been asked, and do not break character or
refer to yourself as an AI."""


def _build_message_history(
    turns: list[TranscriptTurn],
    current_panelist_id: str,
    all_panelists: dict[str, PanelistPersona],
) -> list[dict]:
    """
    Anthropic's API only has 'user' and 'assistant' roles. From the CURRENT panelist's
    point of view: their own past questions are 'assistant', everything else
    (the student's answers AND other panelists' questions) is 'user' context.
    Other panelists' lines are prefixed with their name so the model can distinguish
    multi-party conversation from a simple back-and-forth.
    """
    messages: list[dict] = []
    for turn in turns:
        if turn.speaker_type == SpeakerType.USER:
            messages.append({"role": "user", "content": f"[Student]: {turn.text}"})
        elif turn.panelist_id == current_panelist_id:
            messages.append({"role": "assistant", "content": turn.text})
        else:
            other = all_panelists.get(turn.panelist_id)
            other_name = other.name if other else "Panelist"
            messages.append({"role": "user", "content": f"[{other_name}]: {turn.text}"})
    return messages


async def _generate_with_anthropic(
    persona: PanelistPersona,
    scenario: ScenarioType,
    topic: str,
    messages: list[dict],
    client: AsyncAnthropic,
    document_context: list[str] | None = None,
) -> NextQuestion:
    response = await client.messages.create(
        model=ANTHROPIC_MODEL,
        max_tokens=400,
        system=build_system_prompt(persona, scenario, topic, document_context),
        messages=messages,
        tools=[NEXT_QUESTION_TOOL],
        tool_choice={"type": "tool", "name": "ask_question"},
    )

    tool_use_block = next(b for b in response.content if b.type == "tool_use")
    return NextQuestion.model_validate(tool_use_block.input)


_GEMINI_ROLE_MAP = {"assistant": "model", "user": "user"}


def _to_gemini_contents(messages: list[dict]) -> list[genai_types.Content]:
    """Anthropic uses 'assistant'/'user'; Gemini uses 'model'/'user' for the same roles."""
    return [
        genai_types.Content(role=_GEMINI_ROLE_MAP[m["role"]], parts=[genai_types.Part(text=m["content"])])
        for m in messages
    ]


async def _generate_with_gemini(
    persona: PanelistPersona,
    scenario: ScenarioType,
    topic: str,
    messages: list[dict],
    client: genai.Client,
    document_context: list[str] | None = None,
) -> NextQuestion:
    response = await client.aio.models.generate_content(
        model=GEMINI_MODEL,
        contents=_to_gemini_contents(messages),
        config=genai_types.GenerateContentConfig(
            system_instruction=build_system_prompt(persona, scenario, topic, document_context),
            response_mime_type="application/json",
            response_schema=NextQuestion,
        ),
    )
    return NextQuestion.model_validate_json(response.text)


async def generate_next_question(
    persona: PanelistPersona,
    scenario: ScenarioType,
    topic: str,
    transcript_history: list[TranscriptTurn],
    all_panelists: dict[str, PanelistPersona],
    gemini_client: genai.Client,
    anthropic_client: AsyncAnthropic | None = None,
    document_context: list[str] | None = None,
) -> NextQuestion:
    """
    Primary provider is Gemini. If the Gemini call itself fails (rate limit, out of
    quota, auth, connection, etc. — anything under google.genai.errors.APIError),
    transparently retry the same turn on Anthropic instead of bubbling up to the
    caller's generic "Can you expand further on that point?" fallback. A malformed
    response that fails NextQuestion validation is NOT retried here — that's a bug,
    not a provider-availability problem, and should surface to the caller as-is.

    document_context, when provided (i.e. the session has an attached, embedded
    document), is a handful of the most relevant chunks for the current turn —
    the panelist is instructed to ground its question in them over general knowledge.
    """
    messages = _build_message_history(transcript_history, persona.id, all_panelists)
    if not messages:
        messages = [{"role": "user", "content": "[Session begins. Ask your opening question.]"}]

    try:
        return await _generate_with_gemini(
            persona, scenario, topic, messages, gemini_client, document_context
        )
    except genai_errors.APIError as exc:
        if anthropic_client is None:
            raise

        logger.warning(
            "Gemini call failed, falling back to Anthropic",
            extra={"panelist_id": persona.id, "error": str(exc)},
        )
        return await _generate_with_anthropic(
            persona, scenario, topic, messages, anthropic_client, document_context
        )
