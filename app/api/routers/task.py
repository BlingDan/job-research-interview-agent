from fastapi import APIRouter, HTTPException

from app.core.config import get_settings
from app.integrations.fake_lark_client import FakeLarkClient
from app.integrations.hybrid_lark_client import HybridLarkClient
from app.integrations.lark_cli_client import LarkCliClient
from app.integrations.lark_client import LarkClient
from app.schemas.agent_pilot import (
    AgentPilotResponse,
    TaskActionRequest,
    TaskCreateRequest,
)
from app.services.orchestrator import AgentPilotOrchestrator
from app.services.state_service import StateService


router = APIRouter(tags=["tasks"])


def build_orchestrator() -> AgentPilotOrchestrator:
    settings = get_settings()
    state_service = StateService(settings.workspace_root)
    im_mode = settings.lark_im_mode or settings.lark_mode
    artifact_mode = settings.lark_artifact_mode or settings.lark_mode
    im_client = _build_lark_client(im_mode, settings.lark_cli_timeout_seconds)
    artifact_client = _build_lark_client(
        artifact_mode, settings.lark_cli_timeout_seconds
    )
    if im_mode == artifact_mode:
        lark_client = im_client
    else:
        lark_client = HybridLarkClient(
            im_client=im_client,
            artifact_client=artifact_client,
        )
    return AgentPilotOrchestrator(state_service, lark_client)


def _build_lark_client(mode: str, timeout_seconds: float) -> LarkClient:
    if mode == "real":
        return LarkCliClient(dry_run=False, timeout_seconds=timeout_seconds)
    if mode == "dry_run":
        return LarkCliClient(dry_run=True, timeout_seconds=timeout_seconds)
    return FakeLarkClient()


@router.post("/tasks", response_model=AgentPilotResponse)
def create_task(payload: TaskCreateRequest):
    return build_orchestrator().create_task(payload)


@router.post("/tasks/{task_id}/confirm", response_model=AgentPilotResponse)
def confirm_task(task_id: str):
    try:
        return build_orchestrator().confirm_task(task_id)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail="task not found") from exc


@router.post("/tasks/{task_id}/revise", response_model=AgentPilotResponse)
def revise_task(task_id: str, payload: TaskActionRequest):
    instruction = payload.instruction or payload.message or ""
    if not instruction.strip():
        raise HTTPException(status_code=400, detail="revision instruction is required")
    try:
        return build_orchestrator().revise_task(task_id, instruction)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail="task not found") from exc


@router.get("/tasks/{task_id}", response_model=AgentPilotResponse)
def get_task(task_id: str):
    try:
        return build_orchestrator().get_task(task_id)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail="task not found") from exc
