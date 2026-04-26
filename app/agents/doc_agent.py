from __future__ import annotations

from app.schemas.agent_pilot import AgentPilotTask


def build_doc_artifact(task: AgentPilotTask) -> str:
    return build_fallback_doc(task)


def build_fallback_doc(task: AgentPilotTask) -> str:
    revision_note = ""
    if task.revisions:
        revision_note = "\n\n## 修改记录\n" + "\n".join(
            f"- {item.instruction}" for item in task.revisions
        )

    return f"""# Agent-Pilot 参赛方案

## 1. 项目定位

Agent-Pilot 是一个基于 Feishu IM 的办公协同智能助手。它把需求入口、任务规划、文档生成、演示材料和画板架构串成一条 Feishu 原生闭环。

原始需求：

> {task.input_text}

## 2. Agent 编排

- IM 捕捉自然语言意图，生成任务上下文。
- Planner Agent 拆解任务、选择工具并等待用户确认。
- Doc Agent、Presentation Agent、Canvas Agent 分别生成办公套件产物。
- Orchestrator 用状态机保证确认、进度、修改和交付可追踪。

## 3. 多端协同

- Feishu 是唯一 UI，桌面端和移动端共享同一聊天、同一文档链接、同一演示稿链接。
- `chat_id` 绑定当前任务，用户在同一群聊里查询进度或发起修改。
- 所有 artifact 链接回传到 IM，避免额外 dashboard。

## 4. 飞书办公套件联动

- IM：任务启动、确认、进度查询、修改、最终交付。
- Doc：沉淀参赛方案和结构化说明。
- Slides：生成 5 页答辩汇报材料。
- Canvas/Whiteboard：展示 Agent 编排和办公套件联动架构。

## 5. 工程实现

- FastAPI 提供 Agent-Pilot 任务 API。
- 状态机覆盖 CREATED、PLANNING、WAITING_CONFIRMATION、DOC_GENERATING、PRESENTATION_GENERATING、CANVAS_GENERATING、DELIVERING、DONE、REVISING、FAILED。
- `LarkClient` 抽象真实 `lark-cli` 与 fake/dry-run 模式。
- 本地 fake artifact 保障比赛演示不被权限阻塞。

## 6. 演示亮点

- 不是固定脚本：Planner 输出计划和工具选择。
- 不是自建前端：Feishu IM 作为仪表盘。
- 不是单点生成：Doc、Slides、Canvas 三件套完整联动。
{revision_note}
"""

