from __future__ import annotations

from typing import Literal
from pydantic import BaseModel, Field

from app.schemas.task import TaskCreateRequest
from app.schemas.report import ReportPayload, SearchResultItem

TodoStatus = Literal["pending", "running", "completed", "failed"]

# 展示标题和未来可执行子任务
class TodoItem(BaseModel):
    id: str
    title: str
    intent: str
    query: str
    category: str | None = None
    status: TodoStatus = "pending"
    sources: list[str] = Field(default_factory=list)
    summary_path: str | None = None

# 完成中间研究笔记之后 再汇总
class TaskSummary(BaseModel):
    todo_id: str
    title: str
    category: str | None = None
    question_answered: str
    key_points: list[str] = Field(default_factory=list)
    open_questions: list[str] = Field(default_factory=list)
    needs_followup: bool = False
    followup_queries: list[str] = Field(default_factory=list)
    sources: list[str] = Field(default_factory=list)
    summary_markdown: str
    raw_search_path: str | None = None
    summary_path: str | None = None
    summary_json_path: str | None = None


# 保存整轮任务状态
class ResearchState(BaseModel):
    task_id: str
    input: TaskCreateRequest
    planning: list[TodoItem] = Field(default_factory=list)
    task_summaries: list[TaskSummary] = Field(default_factory=list)
    local_context: str | None = None
    report: ReportPayload | None = None
    search_results: list[SearchResultItem] = Field(default_factory=list)
    status: str = "created"
    error: str | None = None
