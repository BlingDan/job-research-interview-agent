from app.schemas.agent_pilot import (
    AgentPilotTask,
    ArtifactBrief,
    ArtifactRef,
    ToolCallPlan,
    ToolExecutionRecord,
    ToolPlan,
)


def test_task_defaults_start_created():
    task = AgentPilotTask(task_id="task-1", input_text="生成参赛方案")

    assert task.status == "CREATED"
    assert task.artifacts == []
    assert task.revisions == []


def test_artifact_ref_supports_fake_doc():
    artifact = ArtifactRef(
        artifact_id="artifact-1",
        kind="doc",
        title="Agent-Pilot 参赛方案",
        status="fake",
        url="https://fake.feishu.local/doc/task-1",
    )

    assert artifact.kind == "doc"
    assert artifact.status == "fake"


def test_tool_plan_models_agent_visible_feishu_tool_choice():
    call = ToolCallPlan(
        id="create-doc",
        scenario="C",
        capability="create_doc",
        preferred_adapter="mcp",
        fallback_adapters=["lark_cli", "fake"],
        inputs={"title": "Agent-Pilot 参赛方案", "format": "markdown"},
        expected_output="可分享的飞书文档链接",
        user_visible_reason="用飞书文档沉淀参赛方案。",
    )
    plan = ToolPlan(tool_calls=[call])

    assert plan.tool_calls[0].scenario == "C"
    assert plan.tool_calls[0].fallback_adapters == ["lark_cli", "fake"]


def test_task_can_persist_artifact_brief_and_tool_records():
    brief = ArtifactBrief(
        task_summary="生成飞书比赛参赛方案。",
        official_requirement_mapping={"A": "IM 意图入口"},
        must_have_points=["覆盖 Agent 编排"],
        good_to_have_points=["权限失败时可 fallback"],
        agent_architecture=["PlannerAgent -> ToolLayer -> Feishu"],
        multi_end_collaboration_story=["桌面端和移动端共享同一聊天任务"],
        feishu_suite_linkage=["IM -> Doc -> Slides -> Whiteboard -> IM"],
        engineering_implementation_points=["状态机驱动执行"],
        demo_script=["发送 @Agent 参赛任务", "回复确认"],
        risk_and_fallback_story=["真实文档权限不足时使用 fake artifact"],
    )
    record = ToolExecutionRecord(
        call_id="create-doc",
        adapter="lark_cli",
        status="planned",
    )

    task = AgentPilotTask(
        task_id="task-1",
        input_text="生成参赛方案",
        artifact_brief=brief,
        tool_executions=[record],
    )
    restored = AgentPilotTask.model_validate(task.model_dump())

    assert restored.artifact_brief is not None
    assert restored.artifact_brief.official_requirement_mapping["A"] == "IM 意图入口"
    assert restored.tool_executions[0].adapter == "lark_cli"
