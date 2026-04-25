from __future__ import annotations

import json
import re
import uuid
from pathlib import Path

from app.core.config import get_settings
from app.schemas.memory import (
    CandidateProfile,
    MemoryBundle,
    MemoryEvent,
    ProjectMemory,
    SessionMemory,
    SkillMemory,
    WeakPointMemory,
    utc_now_iso,
)
from app.schemas.state import ResearchState


CANDIDATE_PROFILE_FILENAME = "candidate_profile.json"
PROJECT_MEMORY_FILENAME = "project_memory.md"
MEMORY_EVENTS_FILENAME = "memory_events.jsonl"
CONSOLIDATED_MEMORY_FILENAME = "consolidated_memory.md"

DEFAULT_PROJECT_MEMORY = """# Project Memory

## 项目定位
- 本项目是职位调研与面试准备 Agent，不是通用 RAG 问答系统。
- 主链路是 Planner Agent -> Search/Retriever Tool -> Task Summarizer -> Report Writer -> Workspace 落盘。

## 关键设计取舍
- RAG 用于本地资料利用，Search 用于公开资料，Memory 用于跨任务候选人画像。
- Memory 存跨任务稳定事实，不保存完整聊天历史。

## 面试表达
- Agent 体现为任务拆解、工具边界、阶段总结、报告生成和状态可追踪。
- RAG 采用父子块、向量检索 + BM25、RRF、metadata filter。
- Memory 采用文件化轻量实现，后续可替换为 Mem0 / LangMem / 图谱型 memory。
"""

KNOWN_SKILLS = [
    "Python",
    "FastAPI",
    "RAG",
    "LangChain",
    "FAISS",
    "BM25",
    "RRF",
    "Tavily",
    "SSE",
    "LLM",
    "Agent",
]


def get_memory_dir() -> Path:
    memory_dir = Path(get_settings().workspace_root) / "memory"
    memory_dir.mkdir(parents=True, exist_ok=True)
    return memory_dir


def load_candidate_profile() -> CandidateProfile:
    path = get_memory_dir() / CANDIDATE_PROFILE_FILENAME
    if not path.exists():
        return CandidateProfile()

    data = json.loads(path.read_text(encoding="utf-8"))
    return CandidateProfile.model_validate(data)


def save_candidate_profile(profile: CandidateProfile) -> Path:
    path = get_memory_dir() / CANDIDATE_PROFILE_FILENAME
    path.write_text(
        json.dumps(profile.model_dump(mode="json"), ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    return path


def ensure_default_project_memory() -> Path:
    path = get_memory_dir() / PROJECT_MEMORY_FILENAME
    if not path.exists():
        path.write_text(DEFAULT_PROJECT_MEMORY, encoding="utf-8")
    return path


def load_project_memory() -> str:
    path = ensure_default_project_memory()
    return path.read_text(encoding="utf-8")


def load_consolidated_memory() -> str | None:
    path = get_memory_dir() / CONSOLIDATED_MEMORY_FILENAME
    if not path.exists():
        return None
    content = path.read_text(encoding="utf-8").strip()
    return content or None


def save_consolidated_memory(content: str) -> Path:
    path = get_memory_dir() / CONSOLIDATED_MEMORY_FILENAME
    path.write_text(content, encoding="utf-8")
    return path


def load_memory_bundle() -> MemoryBundle:
    profile = load_candidate_profile()
    project_memory = load_project_memory()
    consolidated_memory = load_consolidated_memory()
    if consolidated_memory is None:
        consolidated_memory = render_consolidated_memory(profile, project_memory)

    return MemoryBundle(
        candidate_profile=profile,
        project_memory=project_memory,
        consolidated_memory=consolidated_memory,
    )


def build_session_memory(
    state: ResearchState,
    *,
    report_path: str | None = None,
) -> SessionMemory:
    visited_sources = _unique(
        [
            *(result.source for result in state.search_results),
            *(source for summary in state.task_summaries for source in summary.sources),
        ]
    )
    key_findings = _unique(
        point
        for summary in state.task_summaries
        for point in summary.key_points
    )
    open_questions = _unique(
        question
        for summary in state.task_summaries
        for question in summary.open_questions
    )

    local_context = (state.local_context or "").strip()
    local_context_used = bool(local_context) and "未命中" not in local_context and "没有可用索引" not in local_context

    return SessionMemory(
        task_id=state.task_id,
        planning_titles=[item.title for item in state.planning],
        visited_sources=visited_sources,
        local_context_used=local_context_used,
        local_context_summary=local_context or None,
        key_findings=key_findings,
        candidate_signals=_extract_candidate_signals(state),
        open_questions=open_questions,
        report_path=report_path,
    )


def persist_session_memory(task_dir: Path, memory: SessionMemory) -> Path:
    task_dir.mkdir(parents=True, exist_ok=True)
    path = task_dir / "session_memory.json"
    path.write_text(
        json.dumps(memory.model_dump(mode="json"), ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    return path


def extract_memory_events(
    state: ResearchState,
    session_memory: SessionMemory,
) -> list[MemoryEvent]:
    events: list[MemoryEvent] = []
    candidate_text = "\n".join(
        item
        for item in [
            state.input.user_note or "",
            state.local_context or "",
            session_memory.local_context_summary or "",
            *session_memory.candidate_signals,
        ]
        if item.strip()
    )

    for skill in _extract_known_skills(candidate_text):
        events.append(
            _make_event(
                state.task_id,
                "candidate_skill",
                f"候选人具备 {skill} 相关经验",
                evidence=_truncate(candidate_text),
                confidence=0.85,
            )
        )

    project_name = _extract_project_name(candidate_text)
    if project_name:
        events.append(
            _make_event(
                state.task_id,
                "candidate_project",
                project_name,
                evidence=_truncate(candidate_text),
                confidence=0.8,
            )
        )

    weak_point = _extract_weak_point(candidate_text)
    if weak_point:
        events.append(
            _make_event(
                state.task_id,
                "weak_point",
                weak_point,
                evidence=_truncate(candidate_text),
                confidence=0.75,
            )
        )

    if state.input.interview_topic:
        events.append(
            _make_event(
                state.task_id,
                "interview_focus",
                state.input.interview_topic.strip(),
                evidence="来自本轮 interview_topic",
                confidence=0.8,
            )
        )
        events.append(
            _make_event(
                state.task_id,
                "target_role",
                state.input.interview_topic.strip(),
                evidence="来自本轮 interview_topic",
                confidence=0.7,
            )
        )

    return events


def append_memory_events(events: list[MemoryEvent]) -> Path:
    path = get_memory_dir() / MEMORY_EVENTS_FILENAME
    if not events:
        path.touch(exist_ok=True)
        return path

    with path.open("a", encoding="utf-8") as file:
        for event in events:
            file.write(json.dumps(event.model_dump(mode="json"), ensure_ascii=False))
            file.write("\n")
    return path


def merge_candidate_profile(
    profile: CandidateProfile,
    events: list[MemoryEvent],
) -> CandidateProfile:
    merged = profile.model_copy(deep=True)

    for event in events:
        if event.type == "candidate_skill":
            _merge_skill(merged, event)
        elif event.type == "candidate_project":
            _merge_project(merged, event)
        elif event.type == "target_role":
            _append_unique_value(merged.target_roles, event.content)
        elif event.type == "weak_point":
            _merge_weak_point(merged, event)
        elif event.type == "interview_focus":
            _append_unique_value(merged.interview_focus, event.content)

    merged.updated_at = utc_now_iso()
    return merged


def render_consolidated_memory(
    profile: CandidateProfile,
    project_memory: str,
) -> str:
    skill_names = [skill.name for skill in profile.skills]
    project_names = [project.name for project in profile.projects]
    weak_points = [item.name for item in profile.weak_points if item.status == "active"]

    lines = [
        "# Consolidated Memory",
        "",
        "## Candidate Profile",
        f"- 技能：{_join_or_default(skill_names)}",
        f"- 项目：{_join_or_default(project_names)}",
        f"- 目标岗位：{_join_or_default(profile.target_roles)}",
        f"- 当前弱项：{_join_or_default(weak_points)}",
        f"- 面试重点：{_join_or_default(profile.interview_focus)}",
        "",
        "## Project Memory",
        project_memory.strip() or "暂无项目级记忆。",
        "",
        "## Report Guidance",
        "- 报告要突出岗位匹配点、项目可讲点、差距和下一步准备。",
        "- 公开搜索结果只能作为岗位/公司/面试背景，不能直接作为候选人能力证据。",
    ]
    return "\n".join(lines).strip() + "\n"


def _make_event(
    task_id: str,
    event_type: str,
    content: str,
    *,
    evidence: str | None,
    confidence: float,
) -> MemoryEvent:
    return MemoryEvent(
        id=f"mem_{uuid.uuid4().hex[:12]}",
        task_id=task_id,
        type=event_type,  # type: ignore[arg-type]
        content=content.strip(),
        evidence=evidence,
        confidence=confidence,
    )


def _extract_candidate_signals(state: ResearchState) -> list[str]:
    signals: list[str] = []
    if state.input.user_note and state.input.user_note.strip():
        signals.append(f"用户补充：{state.input.user_note.strip()}")
    if state.local_context and state.local_context.strip():
        signals.append(f"本地资料：{_truncate(state.local_context.strip())}")
    return _unique(signals)


def _extract_known_skills(text: str) -> list[str]:
    found: list[str] = []
    normalized_text = text.lower()
    for skill in KNOWN_SKILLS:
        if skill.lower() in normalized_text:
            found.append(skill)
    return _unique(found)


def _extract_project_name(text: str) -> str | None:
    if "职位调研" in text and "Agent" in text:
        return "职位调研与面试准备 Agent"
    if "项目" in text and "Agent" in text:
        return "Agent 项目经验"
    return None


def _extract_weak_point(text: str) -> str | None:
    patterns = [
        r"([^。！？\n]*(?:需要补强|需要补充|不足|缺少|弱项)[^。！？\n]*)",
        r"([^.!?\n]*(?:need to improve|lack|weak)[^.!?\n]*)",
    ]
    for pattern in patterns:
        match = re.search(pattern, text, flags=re.IGNORECASE)
        if match:
            return match.group(1).strip(" ，,。.")
    return None


def _merge_skill(profile: CandidateProfile, event: MemoryEvent) -> None:
    skill_name = _skill_name_from_event(event)
    existing = _find_by_name(profile.skills, skill_name)
    if existing:
        _append_unique_value(existing.evidence, event.evidence)
        existing.confidence = max(existing.confidence, event.confidence)
        existing.updated_at = utc_now_iso()
        return

    profile.skills.append(
        SkillMemory(
            name=skill_name,
            level="project",
            evidence=[event.evidence] if event.evidence else [],
            confidence=event.confidence,
        )
    )


def _merge_project(profile: CandidateProfile, event: MemoryEvent) -> None:
    project_name = event.content.strip()
    existing = _find_by_name(profile.projects, project_name)
    if existing:
        _append_unique_value(existing.evidence, event.evidence)
        existing.confidence = max(existing.confidence, event.confidence)
        existing.updated_at = utc_now_iso()
        return

    profile.projects.append(
        ProjectMemory(
            name=project_name,
            evidence=[event.evidence] if event.evidence else [],
            confidence=event.confidence,
        )
    )


def _merge_weak_point(profile: CandidateProfile, event: MemoryEvent) -> None:
    name = event.content.strip()
    existing = _find_by_name(profile.weak_points, name)
    if existing:
        _append_unique_value(existing.evidence, event.evidence)
        existing.confidence = max(existing.confidence, event.confidence)
        existing.updated_at = utc_now_iso()
        return

    profile.weak_points.append(
        WeakPointMemory(
            name=name,
            evidence=[event.evidence] if event.evidence else [],
            confidence=event.confidence,
        )
    )


def _skill_name_from_event(event: MemoryEvent) -> str:
    for skill in KNOWN_SKILLS:
        if skill.lower() in event.content.lower():
            return skill
    return event.content.strip()


def _find_by_name(items, name: str):
    normalized_name = name.strip().lower()
    for item in items:
        if item.name.strip().lower() == normalized_name:
            return item
    return None


def _append_unique_value(values: list[str], value: str | None) -> None:
    if not value:
        return
    stripped = value.strip()
    if stripped and stripped not in values:
        values.append(stripped)


def _unique(values) -> list[str]:
    result: list[str] = []
    for value in values:
        if value is None:
            continue
        stripped = str(value).strip()
        if stripped and stripped not in result:
            result.append(stripped)
    return result


def _truncate(text: str, max_chars: int = 500) -> str:
    stripped = " ".join(text.split())
    if len(stripped) <= max_chars:
        return stripped
    return stripped[: max_chars - 3].rstrip() + "..."


def _join_or_default(values: list[str], default: str = "暂无") -> str:
    return "、".join(values) if values else default
