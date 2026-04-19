from pydantic import BaseModel, Field


class PlanningItem(BaseModel):
    step: int
    title: str
    objective: str


class SearchResultItem(BaseModel):
    category: str | None = None
    todo_id: str | None = None
    todo_title: str | None = None # 追溯搜索结果属于哪个任务
    query: str
    title: str
    snippet: str
    source: str


class ReportSection(BaseModel):
    title: str
    bullets: list[str]
    sources: list[str] = Field(default_factory=list) # 让最终报告能够按照 section 追源


class ReportPayload(BaseModel):
    title: str
    summary: str
    sections: list[ReportSection]
    next_actions: list[str]
    references: list[str] = Field(default_factory=list)