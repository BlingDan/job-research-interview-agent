from __future__ import annotations

from fastapi import APIRouter, HTTPException

from app.assistant.runtime import build_orchestrator
from app.agents.intent_router_agent import route_agent_pilot_message
from app.schemas.agent_pilot import AgentPilotResponse, TaskActionRequest


router = APIRouter(prefix="/api/assistant", tags=["assistant"])


@router.get("/tasks/{task_id}", response_model=AgentPilotResponse)
def get_task(task_id: str):
    try:
        return build_orchestrator().get_task(task_id)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail="task not found") from exc


@router.post("/tasks/{task_id}/actions/confirm", response_model=AgentPilotResponse)
def confirm_task(task_id: str):
    try:
        return build_orchestrator().confirm_task(task_id)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail="task not found") from exc


@router.post("/tasks/{task_id}/actions/revise", response_model=AgentPilotResponse)
def revise_task(task_id: str, payload: TaskActionRequest):
    instruction = payload.instruction or payload.message or ""
    if not instruction.strip():
        raise HTTPException(status_code=400, detail="revision instruction is required")
    route = route_agent_pilot_message(instruction)
    try:
        return build_orchestrator().revise_task(
            task_id,
            instruction,
            target_artifacts=route.target_artifacts,
            needs_clarification=route.needs_clarification,
            route_reason=route.reason,
            route_source=route.route_source,
        )
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail="task not found") from exc


@router.post("/tasks/{task_id}/actions/reset", response_model=AgentPilotResponse)
def reset_task(task_id: str):
    orchestrator = build_orchestrator()
    try:
        response = orchestrator.get_task(task_id)
        task = orchestrator.state_service.load_task(task_id)
        if task.chat_id:
            orchestrator.state_service.clear_active_task(task.chat_id)
        return response
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail="task not found") from exc
