from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Literal
from pydantic import BaseModel, Field

EventType = Literal[
    "planning_started",
    "planning_completed",
    "task_started",
    "search_completed",
    "summary_completed",
    "rag_completed",
    "report_completed",
    "error",
]

class ResearchEvent(BaseModel):
    type: EventType
    stage: str
    task_id: str
    message: str
    percentage: int = 0
    payload: dict[str, Any] | None = None
    created_at: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())