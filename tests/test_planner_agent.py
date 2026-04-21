from __future__ import annotations

from app.agents.planner_agent import generate_planning_text
from app.schemas.task import TaskCreateRequest


def test_generate_planning_text_uses_default_model_from_llm_config(monkeypatch) -> None:
    from app.agents import planner_agent

    init_kwargs: dict[str, object] = {}

    class FakeLLM:
        def __init__(self, **kwargs: object):
            init_kwargs.update(kwargs)

        def invoke(self, messages: list[dict[str, str]]) -> str:
            return "[]"

    monkeypatch.setattr(planner_agent, "JobResearchLLM", FakeLLM)

    payload = TaskCreateRequest(jd_text="需要 Python FastAPI Agent 能力")
    result = generate_planning_text(payload)

    assert result == "[]"
    assert init_kwargs["temperature"] == 0.2
    assert init_kwargs["max_tokens"] == 2048
    assert "model" not in init_kwargs
