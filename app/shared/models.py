from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field


TaskStatus = Literal[
    "created",
    "planning",
    "waiting_user",
    "running",
    "delivering",
    "done",
    "revising",
    "failed",
    "archived",
]
TaskStepStatus = Literal[
    "pending",
    "running",
    "waiting_input",
    "done",
    "failed",
    "skipped",
]
TaskActionType = Literal["confirm", "revise", "reset", "retry", "clarify"]
SurfaceType = Literal["im", "cockpit", "windows", "mobile"]


class TaskStep(BaseModel):
    id: str
    title: str
    goal: str = ""
    agent: str = ""
    tool: str = ""
    status: TaskStepStatus = "pending"
    expected_artifact: str | None = None


class TaskArtifact(BaseModel):
    artifact_id: str
    kind: Literal["doc", "slides", "canvas"]
    title: str
    status: str
    url: str | None = None
    summary: str = ""
    local_path: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class TaskAction(BaseModel):
    type: TaskActionType
    label: str
    task_id: str
    description: str = ""
    endpoint: str


class TaskAggregate(BaseModel):
    task_id: str
    input_text: str
    status: TaskStatus
    summary: str | None = None
    chat_id: str | None = None
    message_id: str | None = None
    user_id: str | None = None
    steps: list[TaskStep] = Field(default_factory=list)
    artifacts: list[TaskArtifact] = Field(default_factory=list)
    actions: list[TaskAction] = Field(default_factory=list)
    created_at: str
    updated_at: str
    error: str | None = None


class TaskEvent(BaseModel):
    type: str
    task_id: str
    status: TaskStatus | None = None
    payload: dict[str, Any] = Field(default_factory=dict)


class SurfaceSnapshot(BaseModel):
    surface: SurfaceType
    task: TaskAggregate
    actions: list[TaskAction] = Field(default_factory=list)
    artifacts: list[TaskArtifact] = Field(default_factory=list)
