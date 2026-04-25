from __future__ import annotations

from datetime import datetime, timezone
from typing import Literal

from pydantic import BaseModel, Field


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


MemoryEventType = Literal[
    "candidate_skill",
    "candidate_project",
    "target_role",
    "weak_point",
    "interview_focus",
]


class MemoryEvidence(BaseModel):
    source: str
    content: str


class SkillMemory(BaseModel):
    name: str
    level: str = "unknown"
    evidence: list[str] = Field(default_factory=list)
    confidence: float = 0.7
    updated_at: str = Field(default_factory=utc_now_iso)


class ProjectMemory(BaseModel):
    name: str
    tech_stack: list[str] = Field(default_factory=list)
    highlights: list[str] = Field(default_factory=list)
    evidence: list[str] = Field(default_factory=list)
    confidence: float = 0.7
    updated_at: str = Field(default_factory=utc_now_iso)


class WeakPointMemory(BaseModel):
    name: str
    evidence: list[str] = Field(default_factory=list)
    status: str = "active"
    confidence: float = 0.7
    updated_at: str = Field(default_factory=utc_now_iso)


class CandidateProfile(BaseModel):
    skills: list[SkillMemory] = Field(default_factory=list)
    projects: list[ProjectMemory] = Field(default_factory=list)
    target_roles: list[str] = Field(default_factory=list)
    weak_points: list[WeakPointMemory] = Field(default_factory=list)
    interview_focus: list[str] = Field(default_factory=list)
    preferences: dict[str, str] = Field(default_factory=dict)
    updated_at: str = Field(default_factory=utc_now_iso)


class SessionMemory(BaseModel):
    task_id: str
    planning_titles: list[str] = Field(default_factory=list)
    visited_sources: list[str] = Field(default_factory=list)
    local_context_used: bool = False
    local_context_summary: str | None = None
    key_findings: list[str] = Field(default_factory=list)
    candidate_signals: list[str] = Field(default_factory=list)
    open_questions: list[str] = Field(default_factory=list)
    report_path: str | None = None
    created_at: str = Field(default_factory=utc_now_iso)


class MemoryEvent(BaseModel):
    id: str
    task_id: str
    type: MemoryEventType
    content: str
    evidence: str | None = None
    source: str = "session_memory"
    confidence: float = 0.7
    created_at: str = Field(default_factory=utc_now_iso)


class MemoryBundle(BaseModel):
    candidate_profile: CandidateProfile = Field(default_factory=CandidateProfile)
    project_memory: str = ""
    consolidated_memory: str | None = None
