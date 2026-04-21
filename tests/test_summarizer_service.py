from __future__ import annotations

import json
from pathlib import Path

from app.schemas.report import SearchResultItem
from app.schemas.state import TodoItem
from app.services.summarizer_service import build_task_summary, parse_summary_output


def _make_todo() -> TodoItem:
    return TodoItem(
        id="todo-1",
        title="岗位核心能力拆解",
        intent="提取岗位关键技能",
        query="Python FastAPI Agent workflow requirements",
        category="jd",
    )


def _make_results(source: str = "https://example.com/a") -> list[SearchResultItem]:
    todo = _make_todo()
    return [
        SearchResultItem(
            category="jd",
            todo_id=todo.id,
            todo_title=todo.title,
            query=todo.query,
            title="示例标题",
            snippet="示例摘要",
            source=source,
        )
    ]


def test_parse_summary_output_extracts_json_object_from_markdown_fence() -> None:
    raw_text = """
    ```json
    {
      "question_answered": "该任务回答了岗位核心能力要求。",
      "key_points": ["需要 Python", "需要 FastAPI"],
      "open_questions": [],
      "needs_followup": false,
      "followup_queries": [],
      "sources": ["https://example.com/a"]
    }
    ```
    """

    parsed = parse_summary_output(raw_text)

    assert parsed["question_answered"] == "该任务回答了岗位核心能力要求。"
    assert parsed["key_points"] == ["需要 Python", "需要 FastAPI"]


def test_build_task_summary_persists_json_and_markdown(tmp_path: Path, monkeypatch) -> None:
    from app.services import summarizer_service

    raw_text = """
    {
      "question_answered": "该任务回答了岗位核心能力要求。",
      "key_points": ["需要 Python", "需要 FastAPI", "需要 Agent workflow"],
      "open_questions": [],
      "needs_followup": false,
      "followup_queries": [],
      "sources": ["https://example.com/a", "https://example.com/b"]
    }
    """

    monkeypatch.setattr(
        summarizer_service,
        "generate_summary_text",
        lambda todo, results, local_context=None: raw_text,
    )

    summary = build_task_summary(
        task_id="demo-task",
        todo=_make_todo(),
        results=_make_results(),
        task_dir=tmp_path,
        local_context=None,
    )

    summary_json_path = Path(summary.summary_json_path or "")
    summary_md_path = Path(summary.summary_path or "")

    assert summary.question_answered == "该任务回答了岗位核心能力要求。"
    assert summary_json_path.exists()
    assert summary_md_path.exists()
    assert "需要 Python" in summary_md_path.read_text(encoding="utf-8")

    persisted = json.loads(summary_json_path.read_text(encoding="utf-8"))
    assert persisted["sources"] == ["https://example.com/a", "https://example.com/b"]


def test_build_task_summary_falls_back_when_agent_output_invalid(tmp_path: Path, monkeypatch) -> None:
    from app.services import summarizer_service

    monkeypatch.setattr(
        summarizer_service,
        "generate_summary_text",
        lambda todo, results, local_context=None: "not-json",
    )

    summary = build_task_summary(
        task_id="demo-task",
        todo=_make_todo(),
        results=_make_results(source="empty://tavily"),
        task_dir=tmp_path,
        local_context=None,
    )

    assert summary.needs_followup is True
    assert summary.followup_queries == ["Python FastAPI Agent workflow requirements"]
    assert summary.sources == []
