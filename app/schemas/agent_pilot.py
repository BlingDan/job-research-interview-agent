from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Literal

from pydantic import BaseModel, Field


AgentPilotStatus = Literal[
    "CREATED",
    "PLANNING",
    "WAITING_CONFIRMATION",
    "GENERATING",
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
    "confirm_reset",
    "progress",
    "revise",
    "health",
    "help",
    "reset",
    "clarify",
    "feedback",
    "rehearse",
    "chat",
    "unknown",
]

RouteSource = Literal["llm", "fallback", "hard_command"]


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def feishu_ms_to_utc_iso(millis_str: str) -> str:
    try:
        return datetime.fromtimestamp(
            float(millis_str) / 1000.0, tz=timezone.utc
        ).isoformat()
    except (TypeError, ValueError):
        return utc_now()


def feishu_ms_to_float_seconds(millis_str: str) -> float:
    try:
        return float(millis_str) / 1000.0
    except (TypeError, ValueError):
        return datetime.now(timezone.utc).timestamp()


class PlanStep(BaseModel):
    id: str
    title: str
    goal: str
    agent: str
    tool: str
    expected_artifact: str | None = None


class ChatMessage(BaseModel):
    sender_name: str = ""
    content: str
    timestamp: str | None = None


class AgentPlan(BaseModel):
    summary: str
    steps: list[PlanStep] = Field(default_factory=list)
    confirmation_prompt: str = "回复「确认」后我开始生成文档、汇报材料和画板。"
    tool_plan: ToolPlan | None = None
    confidence: float = 0.5
    clarification_questions: list[str] = Field(default_factory=list)


class ArtifactRef(BaseModel):
    artifact_id: str
    kind: ArtifactKind
    title: str
    url: str | None = None
    token: str | None = None
    local_path: str | None = None
    status: ArtifactStatus
    summary: str = ""
    metadata: dict[str, Any] = Field(default_factory=dict)


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
    consistency_anchors: dict[str, str] = Field(default_factory=dict)


class RevisionRecord(BaseModel):
    revision_id: str
    instruction: str
    target_artifacts: list[ArtifactKind] = Field(default_factory=list)
    summary: str = ""
    change_detail: str = ""
    created_at: str = Field(default_factory=utc_now)


class FeedbackRecord(BaseModel):
    feedback_id: str
    task_id: str
    rating: Literal["helpful", "needs_improvement"] | None = None
    comment: str = ""
    created_at: str = Field(default_factory=utc_now)


class IntentRoute(BaseModel):
    command_type: MessageCommandType
    text: str = ""
    target_artifacts: list[ArtifactKind] = Field(default_factory=list)
    confidence: float = 0.0
    needs_clarification: bool = False
    reason: str = ""
    route_source: RouteSource | None = None


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
    target_artifacts: list[ArtifactKind] = Field(default_factory=list)
    route_confidence: float = 0.0
    needs_clarification: bool = False
    route_reason: str = ""
    route_source: RouteSource | None = None
    event_id: str | None = None
    event_time: float | None = None
    received_at: str = Field(default_factory=utc_now)


class TaskCreateRequest(BaseModel):
    message: str
    chat_id: str | None = None
    message_id: str | None = None
    user_id: str | None = None
    chat_history: list[ChatMessage] = Field(default_factory=list)


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
