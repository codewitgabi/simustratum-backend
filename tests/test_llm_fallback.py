from unittest.mock import AsyncMock

import anthropic
import httpx
import pytest

from api.v1.models.session import ScenarioType
from api.v1.services.llm_service import NextQuestion, PanelistPersona, generate_next_question


def _persona() -> PanelistPersona:
    return PanelistPersona(id="p-1", name="Dr. Okafor", role="Methods", strictness=70, inquisitiveness=60)


def _anthropic_error() -> anthropic.APIError:
    request = httpx.Request("POST", "https://api.anthropic.com/v1/messages")
    return anthropic.BadRequestError(
        message="Your credit balance is too low to access the Anthropic API.",
        response=httpx.Response(400, request=request, json={"error": {"message": "credit balance too low"}}),
        body={"error": {"message": "credit balance too low"}},
    )


@pytest.mark.asyncio
async def test_falls_back_to_gemini_when_anthropic_unavailable(monkeypatch):
    fallback_question = NextQuestion(question_text="Can you justify your sample size?", is_followup=False)

    async def _broken_anthropic(*args, **kwargs):
        raise _anthropic_error()

    async def _working_gemini(*args, **kwargs):
        return fallback_question

    monkeypatch.setattr("api.v1.services.llm_service._generate_with_anthropic", _broken_anthropic)
    monkeypatch.setattr("api.v1.services.llm_service._generate_with_gemini", _working_gemini)

    result = await generate_next_question(
        persona=_persona(),
        scenario=ScenarioType.PROJECT_DEFENSE,
        topic="Sample topic",
        transcript_history=[],
        all_panelists={"p-1": _persona()},
        anthropic_client=AsyncMock(),
        gemini_client=AsyncMock(),
    )

    assert result == fallback_question


@pytest.mark.asyncio
async def test_does_not_fall_back_without_a_gemini_client(monkeypatch):
    async def _broken_anthropic(*args, **kwargs):
        raise _anthropic_error()

    monkeypatch.setattr("api.v1.services.llm_service._generate_with_anthropic", _broken_anthropic)

    with pytest.raises(anthropic.APIError):
        await generate_next_question(
            persona=_persona(),
            scenario=ScenarioType.PROJECT_DEFENSE,
            topic="Sample topic",
            transcript_history=[],
            all_panelists={"p-1": _persona()},
            anthropic_client=AsyncMock(),
            gemini_client=None,
        )


@pytest.mark.asyncio
async def test_validation_errors_are_not_swallowed_into_a_gemini_retry(monkeypatch):
    async def _broken_anthropic(*args, **kwargs):
        raise ValueError("malformed tool response")

    async def _should_not_be_called(*args, **kwargs):
        raise AssertionError("Gemini fallback should not run for non-APIError failures")

    monkeypatch.setattr("api.v1.services.llm_service._generate_with_anthropic", _broken_anthropic)
    monkeypatch.setattr("api.v1.services.llm_service._generate_with_gemini", _should_not_be_called)

    with pytest.raises(ValueError):
        await generate_next_question(
            persona=_persona(),
            scenario=ScenarioType.PROJECT_DEFENSE,
            topic="Sample topic",
            transcript_history=[],
            all_panelists={"p-1": _persona()},
            anthropic_client=AsyncMock(),
            gemini_client=AsyncMock(),
        )
