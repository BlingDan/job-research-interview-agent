from __future__ import annotations

from app.schemas.agent_pilot import ToolCallPlan, ToolPlan


def build_default_tool_plan() -> ToolPlan:
    return ToolPlan(
        tool_calls=[
            ToolCallPlan(
                id="im-intent-capture",
                scenario="A",
                capability="capture_im_intent",
                preferred_adapter="lark_cli",
                fallback_adapters=["fake"],
                inputs={"surface": "Feishu IM"},
                expected_output="绑定到 chat_id/message_id 的任务上下文",
                user_visible_reason="飞书 IM 是比赛要求的一线入口。",
            ),
            ToolCallPlan(
                id="planner-task-decomposition",
                scenario="B",
                capability="plan_task",
                preferred_adapter="mcp",
                fallback_adapters=["lark_cli", "fake"],
                inputs={"agent": "PlannerAgent"},
                expected_output="可确认的 Agent 执行计划",
                user_visible_reason="Planner Agent 显式拆解目标并选择飞书工具。",
            ),
            ToolCallPlan(
                id="doc-create-proposal",
                scenario="C",
                capability="create_doc",
                preferred_adapter="mcp",
                fallback_adapters=["lark_cli", "fake"],
                inputs={"title": "Agent-Pilot 参赛方案", "format": "markdown"},
                expected_output="可分享的飞书文档链接",
                user_visible_reason="用飞书文档沉淀完整参赛方案。",
            ),
            ToolCallPlan(
                id="slides-create-defense",
                scenario="D",
                capability="create_slides",
                preferred_adapter="lark_cli",
                fallback_adapters=["fake"],
                inputs={"title": "Agent-Pilot 5 页答辩汇报材料", "pages": 5},
                expected_output="可分享的飞书幻灯片链接",
                user_visible_reason="用飞书 Slides 支撑现场答辩。",
            ),
            ToolCallPlan(
                id="whiteboard-create-architecture",
                scenario="C",
                capability="create_canvas",
                preferred_adapter="lark_cli",
                fallback_adapters=["fake"],
                inputs={"title": "Agent-Pilot 编排架构画板", "format": "mermaid"},
                expected_output="可分享的飞书画板链接",
                user_visible_reason="用飞书 Canvas/Whiteboard 展示架构和流程。",
            ),
            ToolCallPlan(
                id="im-deliver-summary",
                scenario="F",
                capability="deliver_im_summary",
                preferred_adapter="lark_cli",
                fallback_adapters=["fake"],
                inputs={"surface": "Feishu IM"},
                expected_output="同一 IM 会话中的最终成果摘要",
                user_visible_reason="所有成果回到同一聊天，形成交付闭环。",
            ),
        ]
    )


def find_tool_call(tool_plan: ToolPlan | None, capability: str) -> ToolCallPlan:
    if tool_plan:
        for call in tool_plan.tool_calls:
            if call.capability == capability:
                return call
    for call in build_default_tool_plan().tool_calls:
        if call.capability == capability:
            return call
    raise KeyError(f"No tool call registered for {capability}.")
