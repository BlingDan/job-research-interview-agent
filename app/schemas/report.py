from pydantic import BaseModel

class PlanningItem(BaseModel):
    step: int
    title: str
    objective: str

class SearchResultItem(BaseModel):
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