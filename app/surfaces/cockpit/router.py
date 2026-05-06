from __future__ import annotations

from pathlib import Path

from fastapi import APIRouter, HTTPException

from app.core.config import get_settings
from app.schemas.agent_pilot import AgentPilotResponse
from app.shared.snapshots import summarize_task
from app.shared.state_service import DbStateService


router = APIRouter(prefix="/api/cockpit", tags=["cockpit"])


def _get_state() -> DbStateService:
    return DbStateService(get_settings().workspace_root + "/agent_pilot.db")


@router.get("/tasks")
def list_tasks(status: str | None = None, limit: int = 50):
    state = _get_state()
    tasks = state.list_tasks(limit=limit, status=status)
    return {"tasks": [summarize_task(task) for task in tasks]}


@router.get("/tasks/{task_id}", response_model=AgentPilotResponse)
def get_task_detail(task_id: str):
    state = _get_state()
    task = state.load_task_or_none(task_id)
    if task is None:
        raise HTTPException(status_code=404, detail="task not found")
    return AgentPilotResponse(
        task_id=task.task_id,
        status=task.status,
        plan=task.plan,
        artifact_brief=task.artifact_brief,
        artifacts=task.artifacts,
        tool_executions=task.tool_executions,
        revisions=task.revisions,
        reply="",
        error=task.error,
    )


@router.get("/tasks/{task_id}/artifacts/{kind}")
def get_artifact_content(task_id: str, kind: str):
    state = _get_state()
    task = state.load_task_or_none(task_id)
    if task is None:
        raise HTTPException(status_code=404, detail="task not found")

    artifact = next((item for item in task.artifacts if item.kind == kind), None)
    if artifact is None:
        raise HTTPException(status_code=404, detail="artifact not found")

    content = ""
    if artifact.local_path:
        path = Path(artifact.local_path)
        if path.exists():
            content = path.read_text(encoding="utf-8", errors="replace")

    return {
        "task_id": task_id,
        "kind": kind,
        "title": artifact.title,
        "url": artifact.url,
        "status": artifact.status,
        "summary": artifact.summary,
        "content": content[:20000],
    }
