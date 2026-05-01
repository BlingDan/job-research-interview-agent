from __future__ import annotations

from app.agents.intent_router_agent import (
    build_llm_intent_route,
    route_agent_pilot_message,
)


def test_route_doc_revision_without_prefix():
    route = route_agent_pilot_message("在 Agent-Pilot 参赛方案 中的最后一行添加现在的时间YY-MM-DD HH:MM")

    assert route.command_type == "revise"
    assert route.target_artifacts == ["doc"]
    assert route.needs_clarification is False
    assert route.confidence >= 0.8
    assert route.route_source == "llm"


def test_route_presentation_revision_via_llm(monkeypatch):
    from app.agents import intent_router_agent

    class FakeLLM:
        def __init__(self, **kwargs):
            self.kwargs = kwargs

        def invoke(self, messages):
            return """
            {
              "command_type": "revise",
              "target_artifacts": ["slides"],
              "confidence": 0.88,
              "needs_clarification": false,
              "reason": "user mentioned PPT and strengthening content"
            }
            """

    monkeypatch.setattr(intent_router_agent, "JobResearchLLM", FakeLLM)

    route = route_agent_pilot_message("PPT 第 4 页弱了，强化工程实现和落地路径")

    assert route.command_type == "revise"
    assert route.target_artifacts == ["slides"]
    assert route.needs_clarification is False
    assert route.route_source == "llm"


def test_fallback_no_longer_triggers_revise_on_ambiguous_edit_words():
    route = route_agent_pilot_message("这个方案还需要强化什么？")

    assert route.command_type == "new_task"
    assert route.route_source == "fallback"


def test_fallback_no_longer_matches_generic_canvas_terms():
    route = route_agent_pilot_message("帮我优化一下这个架构")

    assert route.command_type == "new_task"
    assert route.route_source == "fallback"


def test_route_canvas_revision_via_llm(monkeypatch):
    from app.agents import intent_router_agent

    class FakeLLM:
        def __init__(self, **kwargs):
            self.kwargs = kwargs

        def invoke(self, messages):
            return """
            {
              "command_type": "revise",
              "target_artifacts": ["canvas"],
              "confidence": 0.85,
              "needs_clarification": false,
              "reason": "user mentioned architecture diagram update"
            }
            """

    monkeypatch.setattr(intent_router_agent, "JobResearchLLM", FakeLLM)

    route = route_agent_pilot_message("架构图里补一个 MCP fallback 分支和权限失败回退节点")

    assert route.command_type == "revise"
    assert route.target_artifacts == ["canvas"]
    assert route.needs_clarification is False
    assert route.route_source == "llm"


def test_route_ambiguous_revision_requests_clarification():
    route = route_agent_pilot_message("修改：更突出工程实现")

    assert route.command_type == "revise"
    assert route.target_artifacts == []
    assert route.needs_clarification is True
    assert route.route_source == "llm"


def test_route_confirm_reset_hard_command():
    route = route_agent_pilot_message("确认重置")

    assert route.command_type == "confirm_reset"
    assert route.confidence == 1.0
    assert route.route_source == "hard_command"


def test_hard_commands_have_hard_command_source():
    cases = [
        ("/help", "help"),
        ("确认", "confirm"),
        ("/reset", "reset"),
        ("ping", "health"),
        ("当前进度", "progress"),
    ]
    for text, expected_type in cases:
        route = route_agent_pilot_message(text)
        assert route.command_type == expected_type, f"{text!r} → {route.command_type}"
        assert route.route_source == "hard_command", f"{text!r} → {route.route_source}"


def test_llm_router_parses_structured_route(monkeypatch):
    from app.agents import intent_router_agent

    class FakeLLM:
        def __init__(self, **kwargs):
            self.kwargs = kwargs

        def invoke(self, messages):
            return """
            {
              "command_type": "revise",
              "target_artifacts": ["slides"],
              "confidence": 0.93,
              "needs_clarification": false,
              "reason": "用户提到汇报材料和第 5 页，指向 Slides"
            }
            """

    monkeypatch.setattr(intent_router_agent, "JobResearchLLM", FakeLLM)

    route = build_llm_intent_route("把汇报材料第 5 页改得更像比赛收口")

    assert route.command_type == "revise"
    assert route.target_artifacts == ["slides"]
    assert route.confidence == 0.93
    assert route.needs_clarification is False
    assert route.route_source == "llm"
