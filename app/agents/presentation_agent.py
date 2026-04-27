from __future__ import annotations

from app.schemas.agent_pilot import AgentPilotTask, ArtifactBrief
from app.services.artifact_brief_builder import build_artifact_brief


def build_slide_artifact(task: AgentPilotTask) -> list[dict[str, str]]:
    return build_fallback_slides(task)


def build_fallback_slides(task: AgentPilotTask) -> list[dict[str, str]]:
    brief = _brief(task)
    return [
        {
            "title": "Agent-Pilot: 基于 IM 的办公协同智能助手",
            "body": f"{brief.task_summary}\n一句话：从 Feishu IM 发起任务，由 Agent 编排 Doc、Slides、Canvas 并回到 IM 交付。",
        },
        {
            "title": "场景闭环: 从 IM 到办公套件",
            "body": "A-F 场景映射："
            + "；".join(f"{key} {value}" for key, value in brief.official_requirement_mapping.items()),
        },
        {
            "title": "Agent 编排: 状态机与工具调用",
            "body": "；".join(brief.agent_architecture),
        },
        {
            "title": "多端协同: Feishu 作为统一 UI",
            "body": "；".join(brief.multi_end_collaboration_story + brief.feishu_suite_linkage),
        },
        {
            "title": "工程实现与演示路径",
            "body": "；".join(brief.engineering_implementation_points + brief.risk_and_fallback_story),
        },
    ]


def _brief(task: AgentPilotTask) -> ArtifactBrief:
    return task.artifact_brief or build_artifact_brief(task)
