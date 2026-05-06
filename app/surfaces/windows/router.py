from __future__ import annotations

from fastapi import APIRouter, HTTPException

from app.core.config import get_settings
from app.shared.snapshots import build_surface_snapshot, summarize_task
from app.shared.state_service import DbStateService


router = APIRouter(prefix="/api/windows", tags=["windows"])


def _get_state() -> DbStateService:
    return DbStateService(get_settings().workspace_root + "/agent_pilot.db")


@router.get("/home")
def get_home():
    tasks = _get_state().list_tasks(limit=20)
    return {
        "surface": "windows",
        "tasks": [summarize_task(task) for task in tasks],
        "pending_actions": [
            action.model_dump()
            for task in tasks
            for action in build_surface_snapshot(task, "windows").actions
        ],
    }


@router.get("/tasks/{task_id}")
def get_task(task_id: str):
    task = _get_state().load_task_or_none(task_id)
    if task is None:
        raise HTTPException(status_code=404, detail="task not found")
    snapshot = build_surface_snapshot(task, "windows")
    return {"surface": "windows", "snapshot": snapshot.model_dump()}
