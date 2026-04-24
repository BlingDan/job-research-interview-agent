from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace

from app.schemas.report import SearchResultItem
from app.schemas.state import TodoItem
from app.schemas.task import TaskCreateRequest
from app.services.search_service import (
    normalize_search_results,
    prepare_research_context,
    run_task_search,
)


def _make_todo() -> TodoItem:
    return TodoItem(
        id="todo-1",
        title="岗位核心能力拆解",
        intent="提取岗位关键技能",
        query="Python FastAPI Agent workflow requirements",
        category="jd",
    )


def test_normalize_search_results_cleans_text_and_preserves_metadata() -> None:
    todo = _make_todo()
    payload = {
        "results": [
            {
                "title": "FastAPI Agent Overview",
                "source": "https://example.com/agent",
                "snippet": "  FastAPI \n Agent\tworkflow  ",
            }
        ]
    }

    results = normalize_search_results(todo, payload)

    assert len(results) == 1
    assert results[0].title == "FastAPI Agent Overview"
    assert results[0].snippet == "FastAPI Agent workflow"
    assert results[0].todo_id == todo.id


def test_normalize_search_results_supports_tavily_url_and_content() -> None:
    todo = _make_todo()
    payload = {
        "results": [
            {
                "title": "Tavily Result",
                "url": "https://example.com/tavily",
                "content": "  FastAPI \n RAG\tAgent 真实搜索结果  ",
            }
        ]
    }

    results = normalize_search_results(todo, payload)

    assert len(results) == 1
    assert results[0].source == "https://example.com/tavily"
    assert results[0].snippet == "FastAPI RAG Agent 真实搜索结果"


def test_prepare_research_context_filters_invalid_sources_from_summary() -> None:
    results = [
        SearchResultItem(
            category="jd",
            todo_id="todo-1",
            todo_title="岗位核心能力拆解",
            query="query",
            title="有效结果",
            snippet="有效摘要",
            source="https://example.com/a",
        ),
        SearchResultItem(
            category="jd",
            todo_id="todo-1",
            todo_title="岗位核心能力拆解",
            query="query",
            title="占位结果",
            snippet="暂无结果",
            source="empty://tavily",
        ),
    ]

    sources_summary, search_context = prepare_research_context(results)

    assert "https://example.com/a" in sources_summary
    assert "empty://tavily" not in sources_summary
    assert "占位结果" in search_context


def test_run_task_search_persists_deduplicated_artifacts(tmp_path: Path, monkeypatch) -> None:
    from app.services import search_service

    todo = _make_todo()
    payload = TaskCreateRequest(jd_text="需要 Python FastAPI Agent 能力")

    monkeypatch.setattr(
        search_service,
        "get_settings",
        lambda: SimpleNamespace(workspace_root=str(tmp_path)),
    )
    monkeypatch.setattr(
        search_service,
        "dispatch_search",
        lambda query: {
            "results": [
                {
                    "title": "FastAPI Agent Overview",
                    "source": "https://example.com/agent",
                    "snippet": "FastAPI Agent workflow",
                },
                {
                    "title": "FastAPI Agent Overview",
                    "source": "https://example.com/agent",
                    "snippet": "重复结果",
                },
            ],
            "notices": [],
        },
    )

    results, sources_summary, search_context = run_task_search("demo-task", todo, payload)

    task_dir = tmp_path / "tasks" / "demo-task"
    search_json_path = task_dir / "task_1_search.json"
    raw_search_json_path = task_dir / "task_1_raw_search.json"
    sources_md_path = task_dir / "task_1_sources_summary.md"
    context_txt_path = task_dir / "task_1_research_context.txt"
    search_md_path = task_dir / "task_1_search_results.md"

    assert len(results) == 1
    assert "https://example.com/agent" in sources_summary
    assert "FastAPI Agent Overview" in search_context
    assert search_json_path.exists()
    assert raw_search_json_path.exists()
    assert sources_md_path.exists()
    assert context_txt_path.exists()
    assert search_md_path.exists()

    persisted_results = json.loads(search_json_path.read_text(encoding="utf-8"))
    assert len(persisted_results) == 1
    assert persisted_results[0]["source"] == "https://example.com/agent"
