from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Literal

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
CompetitionScenario = Literal["A", "B", "C", "D", "E", "F"]
ToolAdapterName = Literal["mcp", "lark_cli", "fake"]
ToolExecutionStatus = Literal["planned", "running", "succeeded", "fallback", "failed"]
MessageCommandType = Literal[
    "new_task",
    "confirm",
    "progress",
    "revise",
    "health",
    "help",
    "reset",
    "unknown",
]


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
    tool_plan: ToolPlan | None = None


class ArtifactRef(BaseModel):
    artifact_id: str
    kind: ArtifactKind
    title: str
    url: str | None = None
    token: str | None = None
    local_path: str | None = None
    status: ArtifactStatus
    summary: str = ""


class ToolCallPlan(BaseModel):
    id: str
    scenario: CompetitionScenario
    capability: str
    preferred_adapter: ToolAdapterName
    fallback_adapters: list[ToolAdapterName] = Field(default_factory=list)
    inputs: dict[str, Any] = Field(default_factory=dict)
    expected_output: str
    user_visible_reason: str


class ToolPlan(BaseModel):
    tool_calls: list[ToolCallPlan] = Field(default_factory=list)


class ToolExecutionRecord(BaseModel):
    call_id: str
    adapter: str
    status: ToolExecutionStatus
    started_at: str | None = None
    finished_at: str | None = None
    output_ref: ArtifactRef | None = None
    error: str | None = None


class ArtifactBrief(BaseModel):
    task_summary: str
    official_requirement_mapping: dict[CompetitionScenario, str] = Field(default_factory=dict)
    must_have_points: list[str] = Field(default_factory=list)
    good_to_have_points: list[str] = Field(default_factory=list)
    agent_architecture: list[str] = Field(default_factory=list)
    multi_end_collaboration_story: list[str] = Field(default_factory=list)
    feishu_suite_linkage: list[str] = Field(default_factory=list)
    engineering_implementation_points: list[str] = Field(default_factory=list)
    demo_script: list[str] = Field(default_factory=list)
    risk_and_fallback_story: list[str] = Field(default_factory=list)


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
    artifact_brief: ArtifactBrief | None = None
    artifacts: list[ArtifactRef] = Field(default_factory=list)
    tool_executions: list[ToolExecutionRecord] = Field(default_factory=list)
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
    artifact_brief: ArtifactBrief | None = None
    artifacts: list[ArtifactRef] = Field(default_factory=list)
    tool_executions: list[ToolExecutionRecord] = Field(default_factory=list)
    revisions: list[RevisionRecord] = Field(default_factory=list)
    reply: str
    error: str | None = None
