from __future__ import annotations

from datetime import datetime, timezone
from typing import Literal

from pydantic import BaseModel, Field


AgentPilotStatus = Literal[
    "CREATED",
    "PLANNING",
    "WAITING_CONFIRMATION",
    "DOC_GENERATING",
    "PRESENTATION_GENERATING",
    "CANVAS_GENERATING",
    "DELIVERING",
    "DONE",
    "REVISING",
    "FAILED",
]

ArtifactKind = Literal["doc", "slides", "canvas"]
ArtifactStatus = Literal["created", "updated", "fake", "dry_run", "failed"]
MessageCommandType = Literal["new_task", "confirm", "progress", "revise", "health", "unknown"]


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


class PlanStep(BaseModel):
    id: str
    title: str
    goal: str
    agent: str
    tool: str
    expected_artifact: str | None = None


class AgentPlan(BaseModel):
    summary: str
    steps: list[PlanStep] = Field(default_factory=list)
    confirmation_prompt: str = "回复「确认」后我开始生成文档、汇报材料和画板。"


class ArtifactRef(BaseModel):
    artifact_id: str
    kind: ArtifactKind
    title: str
    url: str | None = None
    token: str | None = None
    local_path: str | None = None
    status: ArtifactStatus
    summary: str = ""


class RevisionRecord(BaseModel):
    revision_id: str
    instruction: str
    target_artifacts: list[ArtifactKind] = Field(default_factory=list)
    summary: str = ""
    created_at: str = Field(default_factory=utc_now)


class AgentPilotTask(BaseModel):
    task_id: str
    input_text: str
    chat_id: str | None = None
    message_id: str | None = None
    user_id: str | None = None
    status: AgentPilotStatus = "CREATED"
    plan: AgentPlan | None = None
    artifacts: list[ArtifactRef] = Field(default_factory=list)
    revisions: list[RevisionRecord] = Field(default_factory=list)
    created_at: str = Field(default_factory=utc_now)
    updated_at: str = Field(default_factory=utc_now)
    error: str | None = None


class AgentPilotCommand(BaseModel):
    type: MessageCommandType
    text: str
    chat_id: str | None = None
    message_id: str | None = None
    user_id: str | None = None
    task_id: str | None = None


class TaskCreateRequest(BaseModel):
    message: str
    chat_id: str | None = None
    message_id: str | None = None
    user_id: str | None = None


class TaskActionRequest(BaseModel):
    message: str | None = None
    instruction: str | None = None


class AgentPilotResponse(BaseModel):
    task_id: str
    status: AgentPilotStatus
    plan: AgentPlan | None = None
    artifacts: list[ArtifactRef] = Field(default_factory=list)
    revisions: list[RevisionRecord] = Field(default_factory=list)
    reply: str
    error: str | None = None
