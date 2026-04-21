from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

from app.agents.summarizer_agent import generate_summary_text
from app.schemas.report import SearchResultItem
from app.schemas.state import TaskSummary, TodoItem
from app.tools.note_tool import save_json, save_markdown


def build_task_summary(
    task_id: str,
    todo: TodoItem,
    results: list[SearchResultItem],
    *,
    task_dir: Path,
    local_context: str | None = None,
) -> TaskSummary:
    try:
        raw_text = generate_summary_text(todo, results, local_context=local_context)
        parsed = parse_summary_output(raw_text)
    except Exception:
        parsed = build_fallback_summary(todo, results)

    file_stem = todo.id.replace("todo-", "task_")
    summary_markdown = render_summary_markdown(
        title=todo.title,
        question_answered=parsed["question_answered"],
        key_points=parsed["key_points"],
        open_questions=parsed["open_questions"],
        sources=parsed["sources"],
    )

    summary_json_path = task_dir / f"{file_stem}_summary.json"
    summary_md_path = task_dir / f"{file_stem}_summary.md"

    summary = TaskSummary(
        todo_id=todo.id,
        title=todo.title,
        category=todo.category,
        question_answered=parsed["question_answered"],
        key_points=parsed["key_points"],
        open_questions=parsed["open_questions"],
        needs_followup=parsed["needs_followup"],
        followup_queries=parsed["followup_queries"],
        sources=parsed["sources"],
        summary_markdown=summary_markdown,
        raw_search_path=str(task_dir / f"{file_stem}_search.json"),
        summary_path=str(summary_md_path),
        summary_json_path=str(summary_json_path),
    )

    save_json(summary_json_path, summary.model_dump())
    save_markdown(summary_md_path, summary_markdown)

    return summary


def parse_summary_output(raw_text: str) -> dict[str, Any]:
    text = raw_text.strip()
    if not text:
        raise ValueError("Summarizer returned empty text.")

    try:
        data = json.loads(text)
        if isinstance(data, dict):
            return normalize_summary_dict(data)
    except json.JSONDecodeError:
        pass

    fenced_match = re.search(r"```json\s*(.*?)\s*```", text, re.DOTALL | re.IGNORECASE)
    if fenced_match:
        data = json.loads(fenced_match.group(1).strip())
        if isinstance(data, dict):
            return normalize_summary_dict(data)

    object_match = re.search(r"({.*})", text, re.DOTALL)
    if object_match:
        data = json.loads(object_match.group(1))
        if isinstance(data, dict):
            return normalize_summary_dict(data)

    raise ValueError("Failed to parse summary JSON.")


def normalize_summary_dict(data: dict[str, Any]) -> dict[str, Any]:
    question_answered = str(data.get("question_answered", "")).strip()
    key_points = [str(item).strip() for item in data.get("key_points", []) if str(item).strip()]
    open_questions = [str(item).strip() for item in data.get("open_questions", []) if str(item).strip()]
    followup_queries = [str(item).strip() for item in data.get("followup_queries", []) if str(item).strip()]
    sources = [str(item).strip() for item in data.get("sources", []) if str(item).strip()]
    needs_followup = bool(data.get("needs_followup", False))

    if not question_answered:
        raise ValueError("question_answered cannot be empty.")

    return {
        "question_answered": question_answered,
        "key_points": key_points[:5],
        "open_questions": open_questions[:5],
        "needs_followup": needs_followup,
        "followup_queries": followup_queries[:5],
        "sources": sources,
    }


def build_fallback_summary(todo: TodoItem, results: list[SearchResultItem]) -> dict[str, Any]:
    valid_sources = [item.source for item in results if not item.source.startswith("empty://")]
    key_points = [
        f"{item.title}：{item.snippet}"
        for item in results[:3]
    ]
    if not key_points:
        key_points = ["当前任务没有拿到有效搜索结果，需要后续补搜。"]

    return {
        "question_answered": f"该任务围绕“{todo.title}”收集了初步公开资料。",
        "key_points": key_points,
        "open_questions": ["当前结果不足以支撑高质量总结，可补充更多定向检索。"] if not valid_sources else [],
        "needs_followup": len(valid_sources) == 0,
        "followup_queries": [todo.query] if len(valid_sources) == 0 else [],
        "sources": valid_sources,
    }


def render_summary_markdown(
    *,
    title: str,
    question_answered: str,
    key_points: list[str],
    open_questions: list[str],
    sources: list[str],
) -> str:
    lines = [f"## 任务：{title}", ""]
    lines.append("### 本任务回答的问题")
    lines.append(question_answered)
    lines.append("")
    lines.append("### 关键信息")
    for point in key_points:
        lines.append(f"- {point}")
    if open_questions:
        lines.append("")
        lines.append("### 当前不足")
        for item in open_questions:
            lines.append(f"- {item}")
    lines.append("")
    lines.append("### 主要来源")
    if sources:
        for source in sources:
            lines.append(f"- {source}")
    else:
        lines.append("- 暂无有效来源")
    return "\n".join(lines)