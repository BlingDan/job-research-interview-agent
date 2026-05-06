"""Compatibility exports for Agent-Pilot planning helpers."""

from app.agents.agent_pilot_planner import (
    AGENT_PILOT_PLANNER_SYSTEM_PROMPT,
    build_agent_plan,
    build_fallback_plan,
    build_llm_agent_plan,
    parse_plan_output,
)

PLANNER_SYSTEM_PROMPT = AGENT_PILOT_PLANNER_SYSTEM_PROMPT


def generate_planning_text(message: str) -> str:
    """Return serialized planning output for compatibility callers."""
    plan = build_agent_plan(message)
    return plan.model_dump_json(indent=2, exclude_none=True)


__all__ = [
    "PLANNER_SYSTEM_PROMPT",
    "AGENT_PILOT_PLANNER_SYSTEM_PROMPT",
    "build_agent_plan",
    "build_fallback_plan",
    "build_llm_agent_plan",
    "generate_planning_text",
    "parse_plan_output",
]
