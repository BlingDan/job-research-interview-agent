from __future__ import annotations

from app.schemas.agent_pilot import AgentPilotTask
from app.shared.models import (
    SurfaceSnapshot,
    TaskAction,
    TaskAggregate,
    TaskArtifact,
    TaskStatus,
    TaskStep,
)


_TASK_STATUS_MAP: dict[str, TaskStatus] = {
    "CREATED": "created",
    "PLANNING": "planning",
    "WAITING_CONFIRMATION": "waiting_user",
    "GENERATING": "running",
    "DELIVERING": "delivering",
    "DONE": "done",
    "REVISING": "revising",
    "FAILED": "failed",
}


def normalize_task_status(status: str) -> TaskStatus:
    return _TASK_STATUS_MAP.get(status, "archived")


def build_surface_snapshot(task: AgentPilotTask, surface: str) -> SurfaceSnapshot:
    actions = _build_actions(task)
    aggregate = TaskAggregate(
        task_id=task.task_id,
        input_text=task.input_text,
        status=normalize_task_status(task.status),
        summary=task.plan.summary if task.plan else None,
        chat_id=task.chat_id,
        message_id=task.message_id,
        user_id=task.user_id,
        steps=[
            TaskStep(
                id=step.id,
                title=step.title,
                goal=step.goal,
                agent=step.agent,
                tool=step.tool,
                expected_artifact=step.expected_artifact,
                status=_derive_step_status(task.status),
            )
            for step in (task.plan.steps if task.plan else [])
        ],
        artifacts=[
            TaskArtifact(
                artifact_id=artifact.artifact_id,
                kind=artifact.kind,
                title=artifact.title,
                status=artifact.status,
                url=artifact.url,
                summary=artifact.summary,
                local_path=artifact.local_path,
                metadata=artifact.metadata,
            )
            for artifact in task.artifacts
        ],
        actions=actions,
        created_at=task.created_at,
        updated_at=task.updated_at,
        error=task.error,
    )
    return SurfaceSnapshot(
        surface=surface,
        task=aggregate,
        actions=actions,
        artifacts=aggregate.artifacts,
    )


def summarize_task(task: AgentPilotTask) -> dict[str, object]:
    snapshot = build_surface_snapshot(task, "cockpit")
    return {
        "task_id": task.task_id,
        "input_text": task.input_text[:120],
        "status": snapshot.task.status,
        "summary": snapshot.task.summary,
        "artifacts": [artifact.model_dump() for artifact in snapshot.artifacts],
        "actions": [action.model_dump() for action in snapshot.actions],
        "created_at": task.created_at,
        "updated_at": task.updated_at,
    }


def build_surface_detail(task: AgentPilotTask, surface: str) -> dict[str, object]:
    snapshot = build_surface_snapshot(task, surface)
    return {
        "surface": surface,
        "task_id": task.task_id,
        "status": snapshot.task.status,
        "snapshot": snapshot.model_dump(),
        "plan": task.plan.model_dump() if task.plan else None,
        "tool_executions": [
            execution.model_dump() for execution in task.tool_executions
        ],
        "revisions": [revision.model_dump() for revision in task.revisions],
        "updated_at": task.updated_at,
        "error": task.error,
    }


def _build_actions(task: AgentPilotTask) -> list[TaskAction]:
    actions: list[TaskAction] = []
    if task.status == "WAITING_CONFIRMATION":
        actions.append(
            TaskAction(
                type="confirm",
                label="Confirm task",
                task_id=task.task_id,
                description="Continue the unified assistant execution plan.",
                endpoint=f"/api/assistant/tasks/{task.task_id}/actions/confirm",
            )
        )
        actions.append(
            TaskAction(
                type="reset",
                label="Reset binding",
                task_id=task.task_id,
                description="Clear the current IM binding and start fresh.",
                endpoint=f"/api/assistant/tasks/{task.task_id}/actions/reset",
            )
        )
    if task.status in {"DONE", "REVISING"}:
        actions.append(
            TaskAction(
                type="revise",
                label="Revise artifact",
                task_id=task.task_id,
                description="Request a focused update for an existing artifact.",
                endpoint=f"/api/assistant/tasks/{task.task_id}/actions/revise",
            )
        )
    if task.status == "FAILED":
        actions.append(
            TaskAction(
                type="retry",
                label="Retry task",
                task_id=task.task_id,
                description="Retry the current task execution flow.",
                endpoint=f"/api/assistant/tasks/{task.task_id}/actions/confirm",
            )
        )
    return actions


def _derive_step_status(task_status: str) -> str:
    if task_status == "DONE":
        return "done"
    if task_status == "WAITING_CONFIRMATION":
        return "waiting_input"
    if task_status in {"GENERATING", "DELIVERING", "REVISING"}:
        return "running"
    if task_status == "FAILED":
        return "failed"
    return "pending"
