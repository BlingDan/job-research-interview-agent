from app.agents.canvas_agent import build_fallback_canvas
from app.agents.doc_agent import build_fallback_doc
from app.agents.planner_agent import build_agent_plan, build_fallback_plan, parse_plan_output
from app.agents.presentation_agent import build_fallback_slides
from app.schemas.agent_pilot import AgentPilotTask


def test_fallback_plan_covers_doc_slides_canvas():
    plan = build_fallback_plan("生成参赛方案")

    artifacts = {step.expected_artifact for step in plan.steps}
    assert "项目方案文档" in artifacts
    assert "5 页汇报演示文稿" in artifacts
    assert "Agent 编排架构图" in artifacts
    assert "确认" in plan.confirmation_prompt
    assert plan.tool_plan is not None
    assert [call.scenario for call in plan.tool_plan.tool_calls] == ["A", "B", "C", "D", "C", "F"]
    assert plan.tool_plan.tool_calls[2].preferred_adapter == "mcp"
    assert "lark_cli" in plan.tool_plan.tool_calls[2].fallback_adapters


def test_parse_plan_output_json():
    plan = parse_plan_output(
        """
        {
          "summary": "计划",
          "confirmation_prompt": "回复确认",
          "steps": [
            {
              "id": "step-1",
              "title": "生成文档",
              "goal": "写方案",
              "agent": "DocAgent",
              "tool": "Feishu Doc",
              "expected_artifact": "文档"
            }
          ]
        }
        """
    )

    assert plan.summary == "计划"
    assert plan.steps[0].agent == "DocAgent"


def test_build_agent_plan_uses_llm_when_agent_planner_enabled(monkeypatch):
    from app.agents import planner_agent

    captured_messages: list[dict[str, str]] = []

    class FakeLLM:
        def __init__(self, **kwargs: object):
            pass

        def invoke(self, messages: list[dict[str, str]]) -> str:
            captured_messages.extend(messages)
            return """
            {
              "summary": "基于飞书 IM 需求生成动态 Agent 计划",
              "confirmation_prompt": "回复「确认」继续",
              "steps": [
                {
                  "id": "step-1",
                  "title": "动态理解需求",
                  "goal": "根据用户输入规划 Doc、Slides 和 Canvas 协同路径",
                  "agent": "PlannerAgent",
                  "tool": "Feishu IM",
                  "expected_artifact": "Agent 执行计划"
                }
              ]
            }
            """

    monkeypatch.setattr(
        planner_agent,
        "get_settings",
        lambda: type("Settings", (), {"agent_pilot_planner_mode": "llm"})(),
    )
    monkeypatch.setattr(planner_agent, "JobResearchLLM", FakeLLM)

    plan = build_agent_plan("帮我基于飞书比赛赛题生成参赛方案")

    assert plan.summary == "基于飞书 IM 需求生成动态 Agent 计划"
    assert plan.steps[0].title == "动态理解需求"
    assert "飞书比赛" in captured_messages[-1]["content"]


def test_build_agent_plan_auto_falls_back_when_llm_fails(monkeypatch):
    from app.agents import planner_agent

    class FailingLLM:
        def __init__(self, **kwargs: object):
            pass

        def invoke(self, messages: list[dict[str, str]]) -> str:
            raise RuntimeError("temporary model outage")

    monkeypatch.setattr(
        planner_agent,
        "get_settings",
        lambda: type("Settings", (), {"agent_pilot_planner_mode": "auto"})(),
    )
    monkeypatch.setattr(planner_agent, "JobResearchLLM", FailingLLM)

    plan = build_agent_plan("生成参赛方案")

    assert plan.summary == build_fallback_plan("生成参赛方案").summary


def test_doc_fallback_contains_keywords():
    task = AgentPilotTask(task_id="task-1", input_text="飞书比赛")

    doc = build_fallback_doc(task)

    assert "Agent 编排" in doc
    assert "多端协同" in doc
    assert "飞书办公套件联动" in doc
    assert "工程实现" in doc
    assert "官方 A-F 场景映射" in doc


def test_slides_fallback_has_five_pages():
    task = AgentPilotTask(task_id="task-1", input_text="飞书比赛")

    slides = build_fallback_slides(task)

    assert len(slides) == 5
    assert slides[0]["title"].startswith("Agent-Pilot")
    assert "A-F" in slides[1]["body"]


def test_canvas_fallback_mentions_full_flow():
    task = AgentPilotTask(task_id="task-1", input_text="飞书比赛")

    canvas = build_fallback_canvas(task)

    assert "Feishu IM" in canvas
    assert "Planner Agent" in canvas
    assert "Feishu Doc" in canvas
    assert "Feishu Slides" in canvas
    assert "Canvas" in canvas
    assert "MCP Tool Layer" in canvas
    assert "A-F" in canvas
