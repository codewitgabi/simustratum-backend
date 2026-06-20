import pytest

from api.v1.models.session import ScenarioType
from api.v1.services.llm_service import PanelistPersona, build_system_prompt


def _persona() -> PanelistPersona:
    return PanelistPersona(id="p-1", name="Dr. Okafor", role="Linguistics", strictness=70, inquisitiveness=60)


@pytest.mark.parametrize("scenario", list(ScenarioType))
def test_every_scenario_has_its_own_prompt_file(scenario):
    # Raises FileNotFoundError if a scenario's template is missing.
    prompt = build_system_prompt(_persona(), scenario, "Sample topic")
    assert "Dr. Okafor" in prompt
    assert "Sample topic" in prompt


def test_scenario_prompts_are_all_distinct():
    prompts = {
        scenario: build_system_prompt(_persona(), scenario, "Sample topic") for scenario in ScenarioType
    }
    assert len(set(prompts.values())) == len(ScenarioType)


def test_tutorial_practice_positions_panelist_as_learner_not_examiner():
    prompt = build_system_prompt(_persona(), ScenarioType.TUTORIAL_PRACTICE, "Sample topic")
    assert "learner" in prompt.lower()
    assert "not interrogate" in prompt.lower() or "not to interrogate" in prompt.lower()


def test_english_proficiency_prompts_for_pronunciation_not_questions():
    prompt = build_system_prompt(_persona(), ScenarioType.ENGLISH_PROFICIENCY, "Sample topic")
    assert "pronounce" in prompt.lower()
    assert "not a q&a" in prompt.lower() or "not a q" in prompt.lower()


@pytest.mark.parametrize("scenario", list(ScenarioType))
def test_every_scenario_instructs_short_single_forward_moving_turn(scenario):
    prompt = build_system_prompt(_persona(), scenario, "Sample topic").lower()
    assert "exactly one" in prompt
    assert "short" in prompt
    assert "move" in prompt
    assert "circle back" in prompt or "do not repeat" in prompt
