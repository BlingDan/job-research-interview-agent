from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace

from app.schemas.memory import (
    CandidateProfile,
    MemoryEvent,
    ProjectMemory,
    SkillMemory,
)
from app.schemas.report import SearchResultItem
from app.schemas.state import ResearchState, TaskSummary, TodoItem
from app.schemas.task import TaskCreateRequest
from app.services import memory_service


def _patch_workspace(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setattr(
        memory_service,
        "get_settings",
        lambda: SimpleNamespace(workspace_root=str(tmp_path)),
    )


def test_load_candidate_profile_returns_empty_profile_when_file_missing(tmp_path: Path, monkeypatch) -> None:
    _patch_workspace(monkeypatch, tmp_path)

    profile = memory_service.load_candidate_profile()

    assert profile.skills == []
    assert profile.projects == []
    assert profile.target_roles == []
    assert not (tmp_path / "memory" / "candidate_profile.json").exists()


def test_save_and_load_candidate_profile_round_trips_utf8(tmp_path: Path, monkeypatch) -> None:
    _patch_workspace(monkeypatch, tmp_path)
    profile = CandidateProfile(
        skills=[
            SkillMemory(
                name="FastAPI",
                level="project",
                evidence=["项目中使用 FastAPI 暴露 /tasks 接口"],
                confidence=0.9,
            )
        ],
        target_roles=["AI 应用后端"],
    )

    memory_service.save_candidate_profile(profile)

    loaded = memory_service.load_candidate_profile()
    raw_text = (tmp_path / "memory" / "candidate_profile.json").read_text(encoding="utf-8")

    assert loaded.skills[0].name == "FastAPI"
    assert loaded.target_roles == ["AI 应用后端"]
    assert "项目中使用 FastAPI" in raw_text


def test_project_memory_initialization_does_not_overwrite_existing_file(
    tmp_path: Path,
    monkeypatch,
) -> None:
    _patch_workspace(monkeypatch, tmp_path)
    memory_dir = tmp_path / "memory"
    memory_dir.mkdir(parents=True)
    project_memory_path = memory_dir / "project_memory.md"
    project_memory_path.write_text("# Custom Memory\n\n- keep me", encoding="utf-8")

    memory_service.ensure_default_project_memory()
    content = memory_service.load_project_memory()

    assert content == "# Custom Memory\n\n- keep me"


def test_append_memory_events_writes_jsonl_lines(tmp_path: Path, monkeypatch) -> None:
    _patch_workspace(monkeypatch, tmp_path)
    events = [
        MemoryEvent(
            id="mem_1",
            task_id="task-1",
            type="candidate_skill",
            content="候选人具备 FastAPI 项目经验",
            evidence="本地资料出现 FastAPI",
            confidence=0.85,
        ),
        MemoryEvent(
            id="mem_2",
            task_id="task-1",
            type="interview_focus",
            content="重点准备 RAG 设计",
            evidence="用户备注",
            confidence=0.8,
        ),
    ]

    memory_service.append_memory_events(events)

    lines = (tmp_path / "memory" / "memory_events.jsonl").read_text(encoding="utf-8").splitlines()
    decoded = [json.loads(line) for line in lines]
    assert [item["id"] for item in decoded] == ["mem_1", "mem_2"]
    assert decoded[0]["content"] == "候选人具备 FastAPI 项目经验"


def test_merge_candidate_profile_deduplicates_skills_and_projects() -> None:
    profile = CandidateProfile(
        skills=[
            SkillMemory(
                name="FastAPI",
                level="project",
                evidence=["旧证据"],
                confidence=0.7,
            )
        ],
        projects=[
            ProjectMemory(
                name="职位调研与面试准备 Agent",
                tech_stack=["FastAPI"],
                highlights=["Planner Agent"],
                evidence=["旧项目证据"],
            )
        ],
    )
    events = [
        MemoryEvent(
            id="mem_skill",
            task_id="task-1",
            type="candidate_skill",
            content="候选人具备 FastAPI 项目经验",
            evidence="新证据",
            confidence=0.95,
        ),
        MemoryEvent(
            id="mem_project",
            task_id="task-1",
            type="candidate_project",
            content="职位调研与面试准备 Agent",
            evidence="报告中出现项目链路",
            confidence=0.9,
        ),
    ]

    merged = memory_service.merge_candidate_profile(profile, events)

    assert [skill.name for skill in merged.skills] == ["FastAPI"]
    assert merged.skills[0].confidence == 0.95
    assert merged.skills[0].evidence == ["旧证据", "新证据"]
    assert [project.name for project in merged.projects] == ["职位调研与面试准备 Agent"]
    assert merged.projects[0].evidence == ["旧项目证据", "报告中出现项目链路"]


def test_build_and_persist_session_memory_from_research_state(tmp_path: Path, monkeypatch) -> None:
    _patch_workspace(monkeypatch, tmp_path)
    state = ResearchState(
        task_id="task-1",
        input=TaskCreateRequest(
            jd_text="需要 FastAPI Agent RAG 能力",
            interview_topic="AI 应用后端",
            user_note="我有 FastAPI + RAG 项目经验，但 SSE 还需要补强。",
        ),
        planning=[
            TodoItem(
                id="todo-1",
                title="岗位能力拆解",
                intent="分析 JD",
                query="FastAPI Agent RAG",
                category="jd",
            )
        ],
        task_summaries=[
            TaskSummary(
                todo_id="todo-1",
                title="岗位能力拆解",
                category="jd",
                question_answered="岗位要求 FastAPI 和 RAG。",
                key_points=["需要 FastAPI", "需要 RAG"],
                open_questions=["SSE 经验需要补充"],
                sources=["https://example.com/jd"],
                summary_markdown="## 岗位能力拆解",
            )
        ],
        search_results=[
            SearchResultItem(
                category="jd",
                todo_id="todo-1",
                todo_title="岗位能力拆解",
                query="FastAPI Agent RAG",
                title="JD",
                snippet="需要 FastAPI",
                source="https://example.com/jd",
            )
        ],
        local_context="本地资料显示候选人做过 FastAPI、RAG、BM25、RRF。",
    )

    session_memory = memory_service.build_session_memory(
        state,
        report_path=str(tmp_path / "tasks" / "task-1" / "report.md"),
    )
    written_path = memory_service.persist_session_memory(tmp_path / "tasks" / "task-1", session_memory)

    assert session_memory.local_context_used is True
    assert session_memory.planning_titles == ["岗位能力拆解"]
    assert "https://example.com/jd" in session_memory.visited_sources
    assert "需要 FastAPI" in session_memory.key_findings
    assert any("FastAPI" in signal for signal in session_memory.candidate_signals)
    assert json.loads(written_path.read_text(encoding="utf-8"))["task_id"] == "task-1"


def test_render_consolidated_memory_includes_profile_and_project_memory() -> None:
    profile = CandidateProfile(
        skills=[SkillMemory(name="FastAPI", level="project", evidence=["本地资料"], confidence=0.9)],
        target_roles=["AI 应用后端"],
        interview_focus=["RAG 设计"],
    )

    rendered = memory_service.render_consolidated_memory(
        profile,
        "# Project Memory\n\n- 本项目是职位调研与面试准备 Agent。",
    )

    assert "# Consolidated Memory" in rendered
    assert "FastAPI" in rendered
    assert "AI 应用后端" in rendered
    assert "职位调研与面试准备 Agent" in rendered


def test_extract_memory_events_does_not_treat_company_name_as_candidate_skill() -> None:
    state = ResearchState(
        task_id="task-1",
        input=TaskCreateRequest(
            jd_text="需要 FastAPI",
            company_name="OpenAI",
            interview_topic="AI 应用后端",
            user_note="目标公司是 OpenAI，我有 FastAPI 项目经验。",
        ),
    )
    session_memory = memory_service.build_session_memory(state)

    events = memory_service.extract_memory_events(state, session_memory)
    skill_contents = [event.content for event in events if event.type == "candidate_skill"]

    assert any("FastAPI" in content for content in skill_contents)
    assert not any("OpenAI" in content for content in skill_contents)
