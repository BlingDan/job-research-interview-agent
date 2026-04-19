from __future__ import annotations
import json
import re
from pathlib import Path
from typing import Any

import httpx
from app.core.config import get_settings
from app.schemas.task import TaskCreateRequest
from app.schemas.report import PlanningItem, SearchResultItem


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


def build_search_queries(payload: TaskCreateRequest) -> list[tuple[str, str]]:
    keywords = _extract_keywords(payload.jd_text)
    keyword_text = " ".join(keywords[:4]) if keywords else "岗位要求 技术栈"

    company = (payload.company_name or "").strip()
    interview_focus = (payload.interview_topic or "").strip() or keyword_text

    jd_query = f"{keyword_text} 岗位要求 技术栈 项目经验"

    company_query = (
        f"{company} 公司 业务 技术栈 团队"
        if company
        else f"{keyword_text} 相关公司 业务 技术栈"
    )

    interview_query = f"{interview_focus} 面试题 高频问题 项目经验"

    return [
        ("jd", jd_query),
        ("company", company_query),
        ("interview", interview_query),
    ]


# 在hello-agent 在搜索层的思路是拆成了dispatch_search 和 prepare_research_context()
# 先调取搜索，再将搜索结果整理成报告层需要的格式，最后再生成报告

def dispatch_search(query: str) -> dict[str, Any]:
    settings = get_settings()

    if not settings.tavily_api_key:
        return {
            "results": [],
            "backend": "tavily",
            "notices": ["未配置 TAVILY_API_KEY"],
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
    category: str,
    query: str,
    payload: dict[str, Any],
) -> list[SearchResultItem]:
    items: list[SearchResultItem] = []

    for raw_item in payload.get("results", []):
        title = raw_item.get("title") or "Untitled"
        source = raw_item.get("url") or "unknown://source"
        snippet = _clean_text(raw_item.get("content") or "")

        if not snippet:
            snippet = "该结果没有返回可用摘要，后续可以考虑开启 include_raw_content。"

        items.append(
            SearchResultItem(
                category=category,
                query=query,
                title=title,
                snippet=snippet,
                source=source,
            )
        )

    if not items:
        notice = "；".join(payload.get("notices", [])) or "本次搜索没有拿到有效结果。"
        items.append(
            SearchResultItem(
                category=category,
                query=query,
                title=f"{category} 暂无结果",
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
        f"类别：{item.category}\n标题：{item.title}\n摘要：{item.snippet}\n来源：{item.source}"
        for item in results
    )

    return sources_summary, context


def run_web_research(
    task_id: str,
    payload: TaskCreateRequest,
    planning: list[PlanningItem],
) -> tuple[list[SearchResultItem], str, str]:
    queries = build_search_queries(payload)

    all_results: list[SearchResultItem] = []
    raw_records: list[dict[str, Any]] = []

    for category, query in queries:
        try:
            raw_payload = dispatch_search(query)
            raw_records.append(
                {
                    "category": category,
                    "query": query,
                    "payload": raw_payload,
                }
            )
            all_results.extend(normalize_search_results(category, query, raw_payload))
        except Exception as exc:
            all_results.append(
                SearchResultItem(
                    category=category,
                    query=query,
                    title=f"{category} 搜索失败",
                    snippet=f"Tavily 请求失败：{exc}",
                    source="error://tavily",
                )
            )

    deduped_results = _deduplicate_results(all_results)
    sources_summary, search_context = prepare_research_context(deduped_results)

    _persist_search_artifacts(
        task_id=task_id,
        payload=payload,
        planning=planning,
        queries=queries,
        results=deduped_results,
        raw_records=raw_records,
        sources_summary=sources_summary,
        search_context=search_context,
    )

    return deduped_results, sources_summary, search_context


def _extract_keywords(jd_text: str, max_keywords: int = 6) -> list[str]:
    lower_text = jd_text.lower()
    found: list[str] = []

    for keyword in TECH_KEYWORDS:
        if keyword.lower() in lower_text and keyword not in found:
            found.append(keyword)
        if len(found) >= max_keywords:
            return found

    fallback_tokens: list[str] = []
    for token in re.split(r"[\s,，。；;、/()\[\]\n]+", jd_text.strip()):
        token = token.strip()
        if len(token) < 2:
            continue
        if token in fallback_tokens:
            continue
        fallback_tokens.append(token)
        if len(fallback_tokens) >= max_keywords:
            break

    return fallback_tokens


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


def _persist_search_artifacts(
    task_id: str,
    payload: TaskCreateRequest,
    planning: list[PlanningItem],
    queries: list[tuple[str, str]],
    results: list[SearchResultItem],
    raw_records: list[dict[str, Any]],
    sources_summary: str,
    search_context: str,
) -> None:
    settings = get_settings()
    task_dir = Path(settings.workspace_root) / "tasks" / task_id
    task_dir.mkdir(parents=True, exist_ok=True)

    (task_dir / "search_queries.json").write_text(
        json.dumps(
            {
                "task_id": task_id,
                "payload": payload.model_dump(),
                "planning": [item.model_dump() for item in planning],
                "queries": [{"category": category, "query": query} for category, query in queries],
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )

    (task_dir / "search_results.json").write_text(
        json.dumps([item.model_dump() for item in results], ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    (task_dir / "raw_search.json").write_text(
        json.dumps(raw_records, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    (task_dir / "research_context.txt").write_text(search_context, encoding="utf-8")
    (task_dir / "sources_summary.md").write_text(sources_summary, encoding="utf-8")

    md_lines = [f"# Search Results for {task_id}", ""]
    for item in results:
        md_lines.extend(
            [
                f"## {item.category} | {item.title}",
                f"- query: {item.query}",
                f"- source: {item.source}",
                f"- snippet: {item.snippet}",
                "",
            ]
        )

    (task_dir / "search_results.md").write_text("\n".join(md_lines), encoding="utf-8")