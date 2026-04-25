import json
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace

import pytest

from app.schemas.rag import LocalContextBundle
from app.schemas.report import ReportPayload, ReportSection, SearchResultItem
from app.schemas.state import TaskSummary, TodoItem
from app.schemas.task import TaskCreateRequest
from app.services.research_coordinator import ResearchCoordinator


def test_write_json_persists_serialized_utf8_content():
    with TemporaryDirectory() as temp_dir:
        coordinator = ResearchCoordinator.__new__(ResearchCoordinator)
        coordinator.task_dir = Path(temp_dir)

        payload = {"message": "你好", "count": 1}

        coordinator._write_json("state.json", payload)

        written = (coordinator.task_dir / "state.json").read_text(encoding="utf-8")

        assert json.loads(written) == payload
        assert '"message": "你好"' in written


def test_merge_local_context_can_be_called_from_coordinator_instance():
    coordinator = ResearchCoordinator.__new__(ResearchCoordinator)

    merged = coordinator._merge_local_context("alpha", " beta ")

    assert merged == "alpha\n\nbeta"


def test_run_executes_pipeline_and_persists_outputs(tmp_path: Path, monkeypatch) -> None:
    from app.services import research_coordinator
    from app.services import memory_service

    payload = TaskCreateRequest(
        jd_text="需要 Python FastAPI Agent 能力",
        company_name="OpenAI",
        interview_topic="Agent backend",
        user_note="我有 FastAPI + RAG 项目经验，SSE 还需要补强。",
    )
    todo = TodoItem(
        id="todo-1",
        title="岗位核心能力拆解",
        intent="提取岗位关键技能",
        query="Python FastAPI Agent workflow requirements",
        category="jd",
    )
    results = [
        SearchResultItem(
            category="jd",
            todo_id=todo.id,
            todo_title=todo.title,
            query=todo.query,
            title="示例标题",
            snippet="示例摘要",
            source="https://example.com/a",
        )
    ]
    summary = TaskSummary(
        todo_id=todo.id,
        title=todo.title,
        category=todo.category,
        question_answered="该任务回答了岗位要求。",
        key_points=["需要 Python"],
        open_questions=[],
        needs_followup=False,
        followup_queries=[],
        sources=["https://example.com/a"],
        summary_markdown="## 任务：岗位核心能力拆解",
        summary_path=str(tmp_path / "tasks" / "demo-task" / "task_1_summary.md"),
        summary_json_path=str(tmp_path / "tasks" / "demo-task" / "task_1_summary.json"),
    )
    report = ReportPayload(
        title="面试准备研究报告",
        summary="已完成研究。",
        sections=[
            ReportSection(
                title="岗位要求拆解",
                bullets=["需要 Python"],
                sources=["https://example.com/a"],
            )
        ],
        next_actions=["整理项目亮点"],
        references=["https://example.com/a"],
    )

    def _build_task_summary(*, task_id, todo, results, task_dir, local_context):
        return summary

    monkeypatch.setattr(
        research_coordinator,
        "get_settings",
        lambda: SimpleNamespace(workspace_root=str(tmp_path)),
    )
    monkeypatch.setattr(
        memory_service,
        "get_settings",
        lambda: SimpleNamespace(workspace_root=str(tmp_path)),
    )
    monkeypatch.setattr(research_coordinator, "build_planning", lambda _: [todo])
    monkeypatch.setattr(
        research_coordinator,
        "run_task_search",
        lambda task_id, todo, payload: (results, "- [jd] 示例标题", "任务：岗位核心能力拆解"),
    )
    monkeypatch.setattr(
        research_coordinator,
        "get_local_context",
        lambda query, doc_types=None: LocalContextBundle(
            query=query,
            summary="本地资料显示候选人有 FastAPI、RAG 和 Agent 项目经验。",
            hits=[],
        ),
    )
    monkeypatch.setattr(research_coordinator, "build_task_summary", _build_task_summary)
    monkeypatch.setattr(research_coordinator, "build_report", lambda state: report)
    monkeypatch.setattr(
        research_coordinator,
        "render_report_markdown",
        lambda report: "# 面试准备研究报告\n\n已完成研究。",
    )

    coordinator = ResearchCoordinator(task_id="demo-task", payload=payload)
    state = coordinator.run()
    task_dir = tmp_path / "tasks" / "demo-task"

    assert state.status == "done"
    assert state.report == report
    assert state.planning[0].status == "completed"
    assert state.planning[0].sources == ["https://example.com/a"]
    assert len(state.task_summaries) == 1
    assert len(state.search_results) == 1
    assert json.loads((task_dir / "planning.json").read_text(encoding="utf-8"))[0]["id"] == "todo-1"
    assert json.loads((task_dir / "report.json").read_text(encoding="utf-8"))["title"] == report.title
    state_json = json.loads((task_dir / "state.json").read_text(encoding="utf-8"))
    assert state_json["status"] == "done"
    assert state_json["session_memory"]["task_id"] == "demo-task"
    assert (task_dir / "report.md").read_text(encoding="utf-8").startswith("# 面试准备研究报告")
    assert (task_dir / "session_memory.json").exists()

    memory_dir = tmp_path / "memory"
    profile_json = json.loads((memory_dir / "candidate_profile.json").read_text(encoding="utf-8"))
    event_lines = (memory_dir / "memory_events.jsonl").read_text(encoding="utf-8").splitlines()
    consolidated = (memory_dir / "consolidated_memory.md").read_text(encoding="utf-8")

    assert "project_memory.md" in {path.name for path in memory_dir.iterdir()}
    assert "FastAPI" in [skill["name"] for skill in profile_json["skills"]]
    assert event_lines
    assert "FastAPI" in consolidated


def test_run_marks_state_failed_and_persists_error(tmp_path: Path, monkeypatch) -> None:
    from app.services import research_coordinator

    payload = TaskCreateRequest(jd_text="需要 Python FastAPI Agent 能力")

    monkeypatch.setattr(
        research_coordinator,
        "get_settings",
        lambda: SimpleNamespace(workspace_root=str(tmp_path)),
    )
    monkeypatch.setattr(
        research_coordinator,
        "build_planning",
        lambda _: (_ for _ in ()).throw(RuntimeError("planner boom")),
    )

    coordinator = ResearchCoordinator(task_id="failed-task", payload=payload)

    with pytest.raises(RuntimeError, match="planner boom"):
        coordinator.run()

    persisted_state = json.loads(
        (tmp_path / "tasks" / "failed-task" / "state.json").read_text(encoding="utf-8")
    )
    assert persisted_state["status"] == "failed"
    assert persisted_state["error"] == "planner boom"
