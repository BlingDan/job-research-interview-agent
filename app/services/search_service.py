import json
import re
from pathlib import Path
from typing import Any

import httpx
from app.core.config import get_settings
from app.schemas.task import TaskCreateRequest
from app.schemas.report import PlanningItem, SearchResultItem
from app.schemas.state import TodoItem


TECH_KEYWORDS = [
    "Python",
    "FastAPI",
    "LangChain",
    "RAG",
    "Agent",
    "LLM",
    "Prompt",
    "Workflow",
    "Redis",
    "Docker",
    "Kubernetes",
    "MySQL",
    "PostgreSQL",
    "MongoDB",
    "Java",
    "Go",
    "React",
    "TypeScript",
    "AWS",
    "Linux",
    "NLP",
    "后端",
    "大模型",
    "检索增强",
    "向量数据库",
    "工作流",
]

def dispatch_search(query:str) -> dict[str, Any]:
    settings = get_settings()

    if not settings.tavily_api_key:
        return {
            "result": [],
            "backend": "tavily",
            "error": "Tavily API key is not configured.",
        }
    
    headers = {
        "Authorization": f"Bearer {settings.tavily_api_key}",
        "Content-Type": "application/json",
    }
    body = {
        "query": query,
        "topic": settings.search_topic,
        "search_depth": settings.search_depth,
        "max_results": settings.search_max_results,
        "include_answer": False,
        "include_raw_content": False,
        "auto_parameters": False,
    }

    with httpx.Client(timeout=settings.search_timeout_seconds) as client:
        response = client.post(settings.tavily_base_url, headers=headers, json=body)
        response.raise_for_status()
        data = response.json()
    
    return {
        "results": data.get("results", []),
        "backend": "tavily",
        "notices": [],
        "answer": data.get("answer"),
        "response_time": data.get("response_time"),
        "request_id": data.get("request_id"),
        "raw": data,
    }


def normalize_search_results(
    todo: TodoItem,
    payload: dict[str, Any],
) -> list[SearchResultItem]:

    items: list[SearchResultItem] = []

    for raw_item in payload.get("results", []):
        title = raw_item.get("title") or "Untitled"
        source = raw_item.get("source") or "Unknown"
        snippet = _clean_text(raw_item.get("snippet") or "", max_length=280)
        if not snippet:
            snippet = "No snippet available, consider turn on 'include_raw_content'"
        
        items.append(
            SearchResultItem(
                category=todo.category,
                todo_id=todo.id,
                todo_title=todo.title,
                query=todo.query,
                title=title,
                snippet=snippet,
                source=source,
            )
        )
    
    if not items:
        notice = "；".join(payload.get("notices", [])) or "本次搜索没有拿到有效结果。"
        items.append(
            SearchResultItem(
                category=todo.category,
                todo_id=todo.id,
                todo_title=todo.title,
                query=todo.query,
                title=f"{todo.title} 暂无结果",
                snippet=notice,
                source="empty://tavily",
            )
        )

    return items

def prepare_research_context(results: list[SearchResultItem]) -> tuple[str, str]:
    valid_results = [
        item for item in results
        if not item.source.startswith(("empty://", "error://", "config://"))
    ]

    sources_summary = "\n".join(
        f"- [{item.category}] {item.title} ({item.source})"
        for item in valid_results
    ) or "- 暂无有效来源"

    context = "\n\n".join(
        f"任务：{item.todo_title}\n类别：{item.category}\n标题：{item.title}\n摘要：{item.snippet}\n来源：{item.source}"
        for item in results
    )

    return sources_summary, context


def run_task_search(
    task_id: str,
    todo: TodoItem,
    payload: TaskCreateRequest,
) -> tuple[list[SearchResultItem], str, str]:
    raw_records: list[dict[str, Any]] = []
    all_results: list[SearchResultItem] = []

    try:
        raw_payload = dispatch_search(todo.query)
        raw_records.append(
            {
                "todo_id": todo.id,
                "todo_title": todo.title,
                "query": todo.query,
                "payload": raw_payload,
            }
        )
        all_results.extend(normalize_search_results(todo, raw_payload))
    except Exception as exc:
        all_results.append(
            SearchResultItem(
                category=todo.category,
                todo_id=todo.id,
                todo_title=todo.title,
                query=todo.query,
                title=f"{todo.title} 搜索失败",
                snippet=f"Tavily 请求失败：{exc}",
                source="error://tavily",
            )
        )

    deduped_results = _deduplicate_results(all_results)
    sources_summary, search_context = prepare_research_context(deduped_results)

    _persist_task_search_artifacts(
        task_id=task_id,
        payload=payload,
        todo=todo,
        results=deduped_results,
        raw_records=raw_records,
        sources_summary=sources_summary,
        search_context=search_context,
    )

    return deduped_results, sources_summary, search_context


def _clean_text(text: str, max_length: int = 280) -> str:
    cleaned = re.sub(r"\s+", " ", text).strip()
    if len(cleaned) <= max_length:
        return cleaned
    return cleaned[: max_length - 3] + "..."

def _deduplicate_results(results: list[SearchResultItem]) -> list[SearchResultItem]:
    seen: set[tuple[str | None, str, str]] = set()
    deduped: list[SearchResultItem] = []

    for item in results:
        key = (item.category, item.source, item.title)
        if key in seen:
            continue
        seen.add(key)
        deduped.append(item)

    return deduped

def _persist_task_search_artifacts(
    task_id: str,
    payload: TaskCreateRequest,
    todo: TodoItem,
    results: list[SearchResultItem],
    raw_records: list[dict[str, Any]],
    sources_summary: str,
    search_context: str,
) -> None:
    settings = get_settings()
    task_dir = Path(settings.workspace_root) / "tasks" / task_id
    task_dir.mkdir(parents=True, exist_ok=True)

    file_stem = todo.id.replace("todo-", "task_")

    (task_dir / f"{file_stem}_search.json").write_text(
        json.dumps([item.model_dump() for item in results], ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    (task_dir / f"{file_stem}_raw_search.json").write_text(
        json.dumps(raw_records, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    (task_dir / f"{file_stem}_sources_summary.md").write_text(
        sources_summary,
        encoding="utf-8",
    )

    (task_dir / f"{file_stem}_research_context.txt").write_text(
        search_context,
        encoding="utf-8",
    )

    md_lines = [f"# Search Results for {todo.title}", ""]
    for item in results:
        md_lines.extend(
            [
                f"## {item.title}",
                f"- query: {item.query}",
                f"- source: {item.source}",
                f"- snippet: {item.snippet}",
                "",
            ]
        )
    (task_dir / f"{file_stem}_search_results.md").write_text(
        "\n".join(md_lines),
        encoding="utf-8",
    )