import pytest

from framework.agent import PROMPT_PATHS, Agent


def test_output_shape_is_the_default_prompt() -> None:
    agent = object.__new__(Agent)

    prompt = agent._get_system_message()

    assert prompt == PROMPT_PATHS["output-shape"].read_text().strip()
    assert "keep each name component as a separate" in prompt
    assert "Include a stable identifier" in prompt
    assert "must not change the requested grain" in prompt
    assert "MUST call `search_guides` at least once" in prompt
    assert "MUST call `submit_answer`" in prompt


@pytest.mark.parametrize("prompt_name", PROMPT_PATHS)
def test_prompt_variants_load_from_their_files(prompt_name: str) -> None:
    agent = object.__new__(Agent)
    agent.prompt_name = prompt_name

    assert agent._get_system_message() == PROMPT_PATHS[prompt_name].read_text().strip()


def test_agent_rejects_unknown_prompt() -> None:
    with pytest.raises(ValueError, match="Unknown prompt"):
        Agent(config=None, tools={}, prompt_name="missing")  # type: ignore[arg-type]
