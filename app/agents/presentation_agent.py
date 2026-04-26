from __future__ import annotations

from app.schemas.agent_pilot import AgentPilotTask


def build_slide_artifact(task: AgentPilotTask) -> list[dict[str, str]]:
    return build_fallback_slides(task)


def build_fallback_slides(task: AgentPilotTask) -> list[dict[str, str]]:
    return [
        {
            "title": "Agent-Pilot: 基于 IM 的办公协同智能助手",
            "body": "从 Feishu IM 发起任务，由 Agent 编排 Doc、Slides、Canvas 并回到 IM 交付。",
        },
        {
            "title": "场景闭环: 从 IM 到办公套件",
            "body": "A 意图捕捉、B 任务规划、C 文档/画板生成、D 演示稿生成、E 多端协同、F 总结交付。",
        },
        {
            "title": "Agent 编排: 状态机与工具调用",
            "body": "Planner 输出计划，Orchestrator 管理确认、生成、修改、失败恢复，工具层统一封装 lark-cli。",
        },
        {
            "title": "多端协同: Feishu 作为统一 UI",
            "body": "桌面端和移动端共享同一 IM 对话、同一文档、同一演示稿和同一画板链接。",
        },
        {
            "title": "工程实现与演示路径",
            "body": "FastAPI + Agent 状态机 + LarkClient mixed real/fake 模式，保障真实 IM 和稳定演示同时成立。",
        },
    ]

