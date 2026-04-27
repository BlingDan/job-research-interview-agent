from __future__ import annotations

from app.schemas.agent_pilot import AgentPilotTask, ArtifactBrief
from app.services.artifact_brief_builder import build_artifact_brief


def build_doc_artifact(task: AgentPilotTask) -> str:
    return build_fallback_doc(task)


def build_fallback_doc(task: AgentPilotTask) -> str:
    brief = _brief(task)
    revision_note = ""
    if task.revisions:
        revision_note = "\n\n## 修改记录\n" + "\n".join(
            f"- {item.instruction}" for item in task.revisions
        )

    return f"""# Agent-Pilot 参赛方案

## 1. 项目定位与赛题理解

{brief.task_summary}

Agent-Pilot 是一个基于 Feishu/Lark IM 的办公协同智能助手。它把需求入口、任务规划、文档生成、演示材料和画板架构串成一条 Feishu 原生闭环，核心目标是证明“飞书就是 UI，Agent 是办公任务驾驶员”。

## 2. 官方 A-F 场景映射

{_bullet_mapping(brief.official_requirement_mapping)}

## 3. Agent 编排

{_bullet_list(brief.agent_architecture)}

## 4. 必须打动评委的能力点

{_bullet_list(brief.must_have_points)}

## 5. 多端协同体验

{_bullet_list(brief.multi_end_collaboration_story)}

## 6. 飞书办公套件联动

{_bullet_list(brief.feishu_suite_linkage)}

## 7. 工程实现

{_bullet_list(brief.engineering_implementation_points)}

## 8. 演示脚本

{_numbered_list(brief.demo_script)}

## 9. 风险与 fallback

{_bullet_list(brief.risk_and_fallback_story)}

## 10. 加分项

{_bullet_list(brief.good_to_have_points)}
{revision_note}
"""


def _brief(task: AgentPilotTask) -> ArtifactBrief:
    return task.artifact_brief or build_artifact_brief(task)


def _bullet_mapping(mapping: dict[str, str]) -> str:
    return "\n".join(f"- {key}: {value}" for key, value in mapping.items())


def _bullet_list(items: list[str]) -> str:
    return "\n".join(f"- {item}" for item in items)


def _numbered_list(items: list[str]) -> str:
    return "\n".join(f"{index}. {item}" for index, item in enumerate(items, start=1))
