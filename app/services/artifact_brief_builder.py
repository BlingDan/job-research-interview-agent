from __future__ import annotations

from collections.abc import Iterable

from app.schemas.agent_pilot import AgentPilotTask, ArtifactBrief


OFFICIAL_REQUIREMENT_MAPPING: dict[str, str] = {
    "A": "意图入口：用户在飞书 IM 中用自然语言发起办公协同任务。",
    "B": "任务理解与规划：Planner Agent 拆解目标、选择工具、生成可确认执行计划。",
    "C": "文档与画板生成：Doc Agent 输出项目方案，Canvas Agent 输出架构/流程画板。",
    "D": "演示材料生成：Presentation Agent 生成 5 页汇报演示文稿。",
    "E": "多端协同：桌面端与移动端共享同一聊天任务、状态、产物链接和修改入口。",
    "F": "总结交付：DeliveryService 将成果摘要和可访问链接回传到同一 IM 会话。",
}


def build_artifact_brief(task: AgentPilotTask) -> ArtifactBrief:
    """Build the shared competition brief consumed by Doc, Slides, and Canvas."""

    plan_steps = task.plan.steps if task.plan else []
    planned_tools = _unique_non_empty(step.tool for step in plan_steps)
    planned_agents = _unique_non_empty(step.agent for step in plan_steps)
    task_summary = (
        "Agent-Pilot 将飞书 IM 中的办公协同需求编排为项目方案文档、汇报演示文稿和架构画板，"
        "重点证明 Agent 编排、多端协同、飞书办公套件联动和工程可落地性。"
    )
    if task.input_text.strip():
        task_summary = f"{task_summary}\n原始需求：{task.input_text.strip()}"

    must_have_points = [
        "清晰覆盖 A-F 场景，从 IM 入口到规划、生成、协同和交付，形成完整闭环。",
        "突出 Agent 编排：Planner、Doc、Presentation、Canvas、Delivery 各司其职，由状态机驱动。",
        "突出多端协同：同一 Feishu/Lark IM 会话在桌面端和移动端保持任务状态与产物链接一致。",
        "突出飞书办公套件联动：IM 负责交互，Doc 沉淀方案，Slides 支撑答辩，Canvas/Whiteboard 展示架构。",
        "突出工程实现：FastAPI、显式状态机、LarkClient 抽象、真实 IM、真实/假 artifact fallback。",
    ]

    consistency_anchors = {
        "产品定位": "基于飞书 IM 的 Agent 编排办公助手",
        "核心架构": "FastAPI + LangChain + MCP + lark-cli 三层 fallback",
        "Agent 数量": "3 个专用 Agent（Doc/Presentation/Canvas）+ Planner + Router",
        "执行流程": "5 步 Pipeline：意图 → 规划 → 确认 → 并行生成 → 交付",
        "产物类型": "Doc 方案文档 + Slides 汇报演示 + Canvas 架构画板",
        "多端协同": "桌面端与移动端共享同一 Feishu 聊天任务状态",
    }

    return ArtifactBrief(
        task_summary=task_summary,
        official_requirement_mapping=OFFICIAL_REQUIREMENT_MAPPING.copy(),
        must_have_points=must_have_points,
        good_to_have_points=[
            "在计划消息中展示工具选择，说明 Agent 不是固定脚本而是在选择飞书能力。",
            "最终交付消息诚实展示真实链接、fallback 链接和后续修改入口，保证演示稳定。",
            "用同一套 brief 驱动 Doc、Slides、Canvas，避免三个产物故事不一致。",
        ],
        consistency_anchors=consistency_anchors,
        agent_architecture=[
            "TaskMessageService 接收 IM 文本，IntentRouterAgent 负责识别确认、进度查询、自然语言修改和 /reset 等命令。",
            f"PlannerAgent 生成执行计划并选择工具：{', '.join(planned_tools) if planned_tools else 'Feishu IM, Doc, Slides, Canvas/Whiteboard'}。",
            f"专业 Agent 分工：{', '.join(planned_agents) if planned_agents else 'DocAgent, PresentationAgent, CanvasAgent, DeliveryService'}。",
            "FeishuToolLayer 将 ToolPlan 路由到 MCP、lark-cli 或 fake fallback。",
            "StateService 记录 CREATED -> PLANNING -> WAITING_CONFIRMATION -> 生成 -> DELIVERING -> DONE/REVISING/FAILED。",
        ],
        multi_end_collaboration_story=[
            "多端入口一致：用户从桌面端或移动端发送同一条 IM 指令即可进入任务。",
            "任务与 chat_id 绑定，确认、进度查询、修改都发生在同一聊天里。",
            "Doc、Slides、Canvas 链接回到 IM，移动端可查看，桌面端可继续编辑。",
            "修改：... 会复用已有任务上下文，只重生成受影响产物。",
        ],
        feishu_suite_linkage=[
            "飞书 IM：自然语言入口、计划确认、状态追踪、最终交付和修改入口。",
            "飞书 Doc：结构化沉淀项目方案、场景映射、工程实现和操作指南。",
            "飞书 Slides：将方案压缩成 5 页汇报路径，突出价值、架构、协同、落地。",
            "飞书 Canvas/Whiteboard：用可视化方式展示 IM、Agent、MCP/CLI、办公套件和 fallback。",
        ],
        engineering_implementation_points=[
            "FastAPI 暴露 /tasks、/confirm、/revise、/status，便于本地和 IM 双入口验证。",
            "Planner Agent 支持 LLM auto 模式，失败时回落 deterministic plan。",
            "lark-cli 负责已经验证稳定的 IM WebSocket、消息回复、文档和白板命令。",
            "MCP Tool Layer 作为 Agent-facing 工具协议，让规划层可表达工具选择。",
            "fake/dry-run artifact 保证权限不足时演示流程不中断。",
        ],
        demo_script=[
            "在飞书群聊中 @Agent 发送办公协同任务。",
            "观察 IM 中立即出现 Planner 正在解析的状态提示。",
            "阅读 Agent 计划，确认 A-F 场景和工具选择后回复「确认」。",
            "等待 Doc、Slides、Canvas 链接回到同一 IM 会话。",
            "发送「现在做到哪了？」查看状态，再发送「修改：PPT 更突出工程实现」验证迭代。",
        ],
        risk_and_fallback_story=[
            "真实 IM 与 artifact 权限解耦，避免用户授权影响 Bot 监听。",
            "MCP 不支持的能力回落到 lark-cli，lark-cli 失败时回落到 fake artifact。",
            "fallback 会保留本地产物和真实格式，让演示继续可讲、可看、可验证。",
        ],
    )


def _unique_non_empty(values: Iterable[object]) -> list[str]:
    result: list[str] = []
    for value in values:
        text = str(value or "").strip()
        if text and text not in result:
            result.append(text)
    return result
