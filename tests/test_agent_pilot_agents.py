from app.agents.canvas_agent import build_fallback_canvas
from app.agents.doc_agent import build_fallback_doc
from app.agents.planner_agent import build_fallback_plan, parse_plan_output
from app.agents.presentation_agent import build_fallback_slides
from app.schemas.agent_pilot import AgentPilotTask


def test_fallback_plan_covers_doc_slides_canvas():
    plan = build_fallback_plan("生成参赛方案")

    artifacts = {step.expected_artifact for step in plan.steps}
    assert "参赛方案文档" in artifacts
    assert "5 页答辩汇报材料" in artifacts
    assert "Agent 编排架构图" in artifacts
    assert "确认" in plan.confirmation_prompt


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


def test_doc_fallback_contains_competition_keywords():
    task = AgentPilotTask(task_id="task-1", input_text="飞书比赛")

    doc = build_fallback_doc(task)

    assert "Agent 编排" in doc
    assert "多端协同" in doc
    assert "飞书办公套件联动" in doc
    assert "工程实现" in doc


def test_slides_fallback_has_five_pages():
    task = AgentPilotTask(task_id="task-1", input_text="飞书比赛")

    slides = build_fallback_slides(task)

    assert len(slides) == 5
    assert slides[0]["title"].startswith("Agent-Pilot")


def test_canvas_fallback_mentions_full_flow():
    task = AgentPilotTask(task_id="task-1", input_text="飞书比赛")

    canvas = build_fallback_canvas(task)

    assert "Feishu IM" in canvas
    assert "Planner Agent" in canvas
    assert "Feishu Doc" in canvas
    assert "Feishu Slides" in canvas
    assert "Canvas" in canvas

