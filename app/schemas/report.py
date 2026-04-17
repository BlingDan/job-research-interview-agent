from pydantic import BaseModel


class PlanningItem(BaseModel):
    step: int
    title: str
    objective: str # 这个字段是为了给后续的 report 提供线索，告诉它为什么要搜这个内容，搜完了之后又该怎么用这个内容

class SearchResultItem(BaseModel):
    category: str | None = None  # 给搜索结果一个标签，否则一但每个query返回多条结果，report层就无法通过数组下标来判断
    query: str
    title: str
    snippet: str
    source: str


class ReportSection(BaseModel):
    title: str
    bullets: list[str]

class ReportPayload(BaseModel):
    title: str
    summary: str
    sections: list[ReportSection]
    next_actions: list[str]