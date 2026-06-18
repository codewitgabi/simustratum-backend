from unittest.mock import AsyncMock

import pytest
from google.genai import errors as genai_errors

from api.v1.models.session import ScenarioType
from api.v1.services.llm_service import NextQuestion, PanelistPersona, generate_next_question


def _persona() -> PanelistPersona:
    return PanelistPersona(id="p-1", name="Dr. Okafor", role="Methods", strictness=70, inquisitiveness=60)


def _gemini_error() -> genai_errors.APIError:
    return genai_errors.ClientError(
        code=429,
        response_json={"error": {"message": "Resource has been exhausted"}},
    )


@pytest.mark.asyncio
async def test_falls_back_to_anthropic_when_gemini_unavailable(monkeypatch):
    fallback_question = NextQuestion(question_text="Can you justify your sample size?", is_followup=False)

    async def _broken_gemini(*args, **kwargs):
        raise _gemini_error()

    async def _working_anthropic(*args, **kwargs):
        return fallback_question

    monkeypatch.setattr("api.v1.services.llm_service._generate_with_gemini", _broken_gemini)
    monkeypatch.setattr("api.v1.services.llm_service._generate_with_anthropic", _working_anthropic)

    result = await generate_next_question(
        persona=_persona(),
        scenario=ScenarioType.PROJECT_DEFENSE,
        topic="Sample topic",
        transcript_history=[],
        all_panelists={"p-1": _persona()},
        gemini_client=AsyncMock(),
        anthropic_client=AsyncMock(),
    )

    assert result == fallback_question


@pytest.mark.asyncio
async def test_does_not_fall_back_without_an_anthropic_client(monkeypatch):
    async def _broken_gemini(*args, **kwargs):
        raise _gemini_error()

    monkeypatch.setattr("api.v1.services.llm_service._generate_with_gemini", _broken_gemini)

    with pytest.raises(genai_errors.APIError):
        await generate_next_question(
            persona=_persona(),
            scenario=ScenarioType.PROJECT_DEFENSE,
            topic="Sample topic",
            transcript_history=[],
            all_panelists={"p-1": _persona()},
            gemini_client=AsyncMock(),
            anthropic_client=None,
        )


@pytest.mark.asyncio
async def test_validation_errors_are_not_swallowed_into_an_anthropic_retry(monkeypatch):
    async def _broken_gemini(*args, **kwargs):
        raise ValueError("malformed structured response")

    async def _should_not_be_called(*args, **kwargs):
        raise AssertionError("Anthropic fallback should not run for non-APIError failures")

    monkeypatch.setattr("api.v1.services.llm_service._generate_with_gemini", _broken_gemini)
    monkeypatch.setattr("api.v1.services.llm_service._generate_with_anthropic", _should_not_be_called)

    with pytest.raises(ValueError):
        await generate_next_question(
            persona=_persona(),
            scenario=ScenarioType.PROJECT_DEFENSE,
            topic="Sample topic",
            transcript_history=[],
            all_panelists={"p-1": _persona()},
            gemini_client=AsyncMock(),
            anthropic_client=AsyncMock(),
        )
