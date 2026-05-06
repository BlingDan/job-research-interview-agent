import json
import re

from typing import Any

from app.agents.report_agent import generate_report_text
from app.schemas.report import ReportPayload, ReportSection
from app.schemas.state import ResearchState


def build_report(state: ResearchState) -> ReportPayload:
    try:
        raw_text = generate_report_text(
            planning=state.planning,
            task_summaries=state.task_summaries,
            local_context_summary=state.local_context,
            candidate_profile=state.candidate_profile,
            project_memory=state.project_memory,
            consolidated_memory=state.consolidated_memory,
        )
        return parse_report_output(raw_text)
    except Exception:
        return build_fallback_report(state)


def parse_report_output(raw_text: str) -> ReportPayload:
    text = raw_text.strip()
    if not text:
        raise ValueError("Report agent returned empty text.")

    try:
        data = json.loads(text)
        if isinstance(data, dict):
            return normalize_report_dict(data)
    except json.JSONDecodeError:
        pass

    fenced_match = re.search(r"```json\s*(.*?)\s*```", text, re.DOTALL | re.IGNORECASE)
    if fenced_match:
        data = json.loads(fenced_match.group(1).strip())
        if isinstance(data, dict):
            return normalize_report_dict(data)

    object_match = re.search(r"({.*})", text, re.DOTALL)
    if object_match:
        data = json.loads(object_match.group(1))
        if isinstance(data, dict):
            return normalize_report_dict(data)

    raise ValueError("Failed to parse report JSON.")


def normalize_report_dict(data: dict[str, Any]) -> ReportPayload:
    sections: list[ReportSection] = []
    for item in data.get("sections", []):
        title = str(item.get("title", "")).strip()
        bullets = [str(line).strip() for line in item.get("bullets", []) if str(line).strip()]
        sources = [str(line).strip() for line in item.get("sources", []) if str(line).strip()]
        if not title:
            continue
        sections.append(ReportSection(title=title, bullets=bullets, sources=sources))

    if not sections:
        raise ValueError("Report sections cannot be empty.")

    title = str(data.get("title", "")).strip() or "面试准备研究报告"
    summary = str(data.get("summary", "")).strip() or "已完成本轮研究。"
    next_actions = [str(line).strip() for line in data.get("next_actions", []) if str(line).strip()]
    references = [str(line).strip() for line in data.get("references", []) if str(line).strip()]

    return ReportPayload(
        title=title,
        summary=summary,
        sections=sections,
        next_actions=next_actions,
        references=references,
    )


def build_fallback_report(state: ResearchState) -> ReportPayload:
    references = sorted(
        {
            source
            for summary in state.task_summaries
            for source in summary.sources
        }
    )

    sections: list[ReportSection] = []
    for summary in state.task_summaries:
        sections.append(
            ReportSection(
                title=summary.title,
                bullets=summary.key_points[:5] or [summary.question_answered],
                sources=summary.sources,
            )
        )

    memory_section = build_memory_matching_section(state)
    if memory_section is not None:
        sections.append(memory_section)

    next_actions = [
        "补充更细的岗位技术映射",
        "补充本地资料与候选人项目经验对应关系",
        "把高频技术问题整理成可复习问答卡片",
    ]

    return ReportPayload(
        title="面试准备研究报告",
        summary="已按规划、执行、汇总三阶段完成研究流程。",
        sections=sections,
        next_actions=next_actions,
        references=references,
    )


def build_memory_matching_section(state: ResearchState) -> ReportSection | None:
    profile = state.candidate_profile
    if profile is None:
        return None

    bullets: list[str] = []
    sources: list[str] = []

    if profile.skills:
        bullets.append(
            "候选人长期技能画像：" + "、".join(skill.name for skill in profile.skills[:8])
        )
        sources.extend(
            evidence
            for skill in profile.skills
            for evidence in skill.evidence[:2]
        )

    if profile.projects:
        bullets.append(
            "可重点讲解的项目经验：" + "、".join(project.name for project in profile.projects[:5])
        )
        sources.extend(
            evidence
            for project in profile.projects
            for evidence in project.evidence[:2]
        )

    if profile.target_roles:
        bullets.append("目标岗位方向：" + "、".join(profile.target_roles[:5]))

    active_weak_points = [
        item.name for item in profile.weak_points if item.status == "active"
    ]
    if active_weak_points:
        bullets.append("需要补齐的候选人弱项：" + "、".join(active_weak_points[:5]))

    if not bullets:
        return None

    return ReportSection(
        title="候选人长期画像与项目匹配",
        bullets=bullets,
        sources=sorted(set(sources)),
    )


def render_report_markdown(report: ReportPayload) -> str:
    lines = [f"# {report.title}", ""]
    lines.append(report.summary)
    lines.append("")

    for section in report.sections:
        lines.append(f"## {section.title}")
        for bullet in section.bullets:
            lines.append(f"- {bullet}")
        if section.sources:
            lines.append("")
            lines.append("### 来源")
            for source in section.sources:
                lines.append(f"- {source}")
        lines.append("")

    if report.next_actions:
        lines.append("## 下一步建议")
        for action in report.next_actions:
            lines.append(f"- {action}")
        lines.append("")

    if report.references:
        lines.append("## 参考来源")
        for ref in report.references:
            lines.append(f"- {ref}")

    return "\n".join(lines)
