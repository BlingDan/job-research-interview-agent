from app.agents.planner_agent import build_fallback_plan
from app.schemas.agent_pilot import AgentPilotTask
from app.services.artifact_brief_builder import build_artifact_brief


def test_artifact_brief_covers_official_a_to_f_requirements():
    task = AgentPilotTask(
        task_id="task-1",
        input_text="帮我基于飞书比赛赛题生成参赛方案，重点突出 Agent 编排、多端协同、飞书办公套件联动和工程实现。",
        plan=build_fallback_plan("生成参赛方案"),
    )

    brief = build_artifact_brief(task)

    assert set(brief.official_requirement_mapping) == {"A", "B", "C", "D", "E", "F"}
    assert any("Agent 编排" in item for item in brief.must_have_points)
    assert any("IntentRouterAgent" in item for item in brief.agent_architecture)
    assert any("多端" in item for item in brief.multi_end_collaboration_story)
    assert any("飞书" in item for item in brief.feishu_suite_linkage)
    assert any("确认" in item for item in brief.demo_script)


def test_artifact_brief_does_not_treat_revision_text_as_content_patch():
    task = AgentPilotTask(
        task_id="task-1",
        input_text="生成参赛方案",
        plan=build_fallback_plan("生成参赛方案"),
    )
    task.revisions.append(
        {
            "revision_id": "rev-1",
            "instruction": "修改：PPT 更突出工程实现和多端协同",
            "target_artifacts": ["slides"],
            "summary": "已处理",
        }
    )

    brief = build_artifact_brief(task)

    assert any("工程实现" in item for item in brief.must_have_points)
    assert not any("修改：PPT" in item for item in brief.must_have_points)
    assert not any("修改：PPT" in item for item in brief.risk_and_fallback_story)
