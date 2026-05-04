from __future__ import annotations

import json

from app.core.llm import JobResearchLLM
from app.schemas.agent_pilot import AgentPilotTask, ArtifactBrief
from app.services.artifact_brief_builder import build_artifact_brief


def build_slide_artifact(task: AgentPilotTask) -> list[dict[str, str]]:
    try:
        result = build_llm_slides(task)
        if len(result) >= 3:
            return result
    except Exception:
        pass
    return build_fallback_slides(task)


def build_llm_slides(task: AgentPilotTask) -> list[dict[str, str]]:
    brief = _brief(task)
    llm = JobResearchLLM(temperature=0.3, max_tokens=4096)
    messages = [
        {
            "role": "system",
            "content": "你是 Agent-Pilot 的 Presentation Agent。根据用户的原始需求和 ArtifactBrief 生成 5 页汇报演示文稿的 JSON 数组。每页包含 title 和 body 字段。只返回 JSON 数组，不要额外解释。",
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

工程实现：
{json.dumps(brief.engineering_implementation_points, ensure_ascii=False)}

请生成 5 页汇报演示文稿的 JSON 数组。""",
        },
    ]
    raw = llm.invoke(messages).strip()
    return _parse_slides_json(raw)


def _parse_slides_json(raw: str) -> list[dict[str, str]]:
    import re

    text = raw.strip()
    try:
        data = json.loads(text)
    except json.JSONDecodeError:
        match = re.search(r"```(?:json)?\s*(.*?)\s*```", text, re.DOTALL)
        if match:
            data = json.loads(match.group(1).strip())
        else:
            match = re.search(r"(\[.*\])", text, re.DOTALL)
            if match:
                data = json.loads(match.group(1))
            else:
                raise

    if not isinstance(data, list):
        raise ValueError("Slides output must be a JSON array")
    return [
        {"title": str(item.get("title", "")), "body": str(item.get("body", ""))}
        for item in data
        if isinstance(item, dict)
    ]


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
