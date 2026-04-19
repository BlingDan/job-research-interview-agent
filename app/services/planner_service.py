"""
调取 planner_agent,
提取 json
校验
fallback
"""
from __future__ import annotations

import json
import re

from app.agents.planner_agent import generate_planning_text
from app.schemas.state import TodoItem
from app.schemas.task import TaskCreateRequest

from typing import Any



ALLOWED_CATEGORIES = {"jd", "company", "interview", "candidate_gap"}

def build_planning(payload: TaskCreateRequest) -> list[TodoItem]:
    try:
        raw_text = generate_planning_text(payload)
        parsed_items = parse_planner_output(raw_text)
        return validate_planning_items(parsed_items)
    except Exception as e:
        print(f"Planner agent failed: {e}")
        print("Falling back to default planning...")
        return build_fallback_planning(payload)

def parse_planner_output(raw_text: str) -> list[dict[str, Any]]:
    text = raw_text.strip()
    if not text:
        raise ValueError("Planner returned empty text.")

    try:
        data = json.loads(text)
        if isinstance(data, list):
            return data
    except json.JSONDecodeError:
        pass

    fenced_match = re.search(r"```json\s*(.*?)\s*```", text, re.DOTALL | re.IGNORECASE)
    if fenced_match:
        fenced_content = fenced_match.group(1).strip()
        data = json.loads(fenced_content)
        if isinstance(data, list):
            return data

    array_match = re.search(r"(\[\s*{.*}\s*\])", text, re.DOTALL)
    if array_match:
        array_content = array_match.group(1)
        data = json.loads(array_content)
        if isinstance(data, list):
            return data

    raise ValueError("Failed to extract planner JSON array.")

def validate_planning_items(items: list[dict[str, Any]]) -> list[TodoItem]:
    if not (3 <= len(items) <= 5):
        raise ValueError("Planner item count must be between 3 and 5.")

    todo_items: list[TodoItem] = []
    seen_titles: set[str] = set()

    for index, item in enumerate(items, start=1):
        title = str(item.get("title", "")).strip()
        intent = str(item.get("intent", "")).strip()
        query = str(item.get("query", "")).strip()
        category = str(item.get("category", "")).strip()

        if not title or not intent or not query:
            raise ValueError("Planner item fields cannot be empty.")

        if len(title) < 4:
            raise ValueError("Planner item title is too short.")

        normalized_title = title.lower()
        if normalized_title in seen_titles:
            raise ValueError("Planner item title is duplicated.")
        seen_titles.add(normalized_title)

        if category not in ALLOWED_CATEGORIES:
            raise ValueError(f"Invalid category: {category}")

        todo_items.append(
            TodoItem(
                id=f"todo-{index}",
                title=title,
                intent=intent,
                query=query,
                category=category,
            )
        )

    return todo_items

def build_fallback_planning(payload: TaskCreateRequest) -> list[TodoItem]:
    company_name = (payload.company_name or "").strip() or "目标公司"
    interview_topic = (payload.interview_topic or "").strip() or "岗位技术面试"
    jd_seed = (payload.jd_text or "").strip()[:80] or "岗位要求"

    return [
        TodoItem(
            id="todo-1",
            title="岗位核心能力拆解",
            intent="提取该岗位在技术、项目和交付上的核心要求",
            query=f"{jd_seed} 岗位要求 技术栈 项目经验",
            category="jd",
        ),
        TodoItem(
            id="todo-2",
            title="公司与业务背景调研",
            intent="梳理目标公司的业务方向、技术栈和团队关注点",
            query=f"{company_name} 公司 业务 技术栈 团队",
            category="company",
        ),
        TodoItem(
            id="todo-3",
            title="高频技术面试点整理",
            intent="整理目标岗位常见的高频技术面试问题",
            query=f"{interview_topic} 高频面试题 项目经验",
            category="interview",
        ),
        TodoItem(
            id="todo-4",
            title="候选人准备方向分析",
            intent="从岗位要求和候选人背景出发，识别准备重点和差距",
            query=f"{jd_seed} 候选人 准备方向 差距分析",
            category="candidate_gap",
        ),
    ]