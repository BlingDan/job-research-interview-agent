from __future__ import annotations

import json

from app.core.llm import JobResearchLLM
from app.schemas.agent_pilot import AgentPilotTask, ArtifactBrief
from app.services.artifact_brief_builder import build_artifact_brief


def build_doc_artifact(task: AgentPilotTask) -> str:
    try:
        result = build_llm_doc(task)
        if len(result) >= 100:
            return result
    except Exception:
        pass
    return build_fallback_doc(task)


def build_llm_doc(task: AgentPilotTask) -> str:
    brief = _brief(task)
    llm = JobResearchLLM(temperature=0.3, max_tokens=4096)
    messages = [
        {
            "role": "system",
            "content": "你是 Agent-Pilot 的 Doc Agent。根据用户的原始需求和 ArtifactBrief 生成一份完整的项目方案 Markdown 文档。结构清晰，覆盖所有必要章节。只返回 Markdown，不要额外解释。",
        },
        {
            "role": "user",
            "content": f"""原始需求：
{task.input_text}

方案摘要：
{brief.task_summary}

A-F 场景映射：
{json.dumps(brief.official_requirement_mapping, ensure_ascii=False)}

核心能力点：
{json.dumps(brief.must_have_points, ensure_ascii=False)}

Agent 架构：
{json.dumps(brief.agent_architecture, ensure_ascii=False)}

多端协同：
{json.dumps(brief.multi_end_collaboration_story, ensure_ascii=False)}

飞书套件联动：
{json.dumps(brief.feishu_suite_linkage, ensure_ascii=False)}

工程实现：
{json.dumps(brief.engineering_implementation_points, ensure_ascii=False)}

演示脚本：
{json.dumps(brief.demo_script, ensure_ascii=False)}

风险与 fallback：
{json.dumps(brief.risk_and_fallback_story, ensure_ascii=False)}

加分项：
{json.dumps(brief.good_to_have_points, ensure_ascii=False)}

请生成完整的项目方案 Markdown 文档。""",
        },
    ]
    return llm.invoke(messages).strip()


def build_fallback_doc(task: AgentPilotTask) -> str:
    brief = _brief(task)

    return f"""# Agent-Pilot 项目方案

## 1. 项目定位与需求理解

{brief.task_summary}

Agent-Pilot 是一个基于 Feishu/Lark IM 的办公协同智能助手。它把需求入口、任务规划、文档生成、演示材料和画板架构串成一条 Feishu 原生闭环，核心理念是”飞书即界面，Agent 是办公任务驾驶员”。

## 2. 官方 A-F 场景映射

{_bullet_mapping(brief.official_requirement_mapping)}

## 3. Agent 编排

{_bullet_list(brief.agent_architecture)}

## 4. 核心能力与亮点

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
"""


def _brief(task: AgentPilotTask) -> ArtifactBrief:
    return task.artifact_brief or build_artifact_brief(task)


def _bullet_mapping(mapping: dict[str, str]) -> str:
    return "\n".join(f"- {key}: {value}" for key, value in mapping.items())


def _bullet_list(items: list[str]) -> str:
    return "\n".join(f"- {item}" for item in items)


def _numbered_list(items: list[str]) -> str:
    return "\n".join(f"{index}. {item}" for index, item in enumerate(items, start=1))
