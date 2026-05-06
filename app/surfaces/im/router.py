from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from app.assistant.runtime import build_orchestrator
from app.services.task_message_service import TaskMessageService


class ImCommandRequest(BaseModel):
    message: str | None = None
    text: str | None = None
    chat_id: str | None = None
    message_id: str | None = None
    user_id: str | None = None
    task_id: str | None = None


class ImEventRequest(BaseModel):
    model_config = {"extra": "allow"}


router = APIRouter(prefix="/api/im", tags=["im"])


@router.post("/commands")
def post_command(payload: ImCommandRequest):
    text = (payload.message or payload.text or "").strip()
    if not text:
        raise HTTPException(status_code=400, detail="message is required")

    command = TaskMessageService().parse_text(
        text,
        chat_id=payload.chat_id,
        message_id=payload.message_id,
        user_id=payload.user_id,
        task_id=payload.task_id,
    )
    response = build_orchestrator().handle_command(command)
    if response is None:
        return {
            "accepted": True,
            "command_type": command.type,
            "chat_id": command.chat_id,
            "message_id": command.message_id,
        }
    return response


@router.post("/events")
def post_event(payload: dict[str, Any]):
    service = TaskMessageService()
    command = service.parse_lark_event(payload)
    response = build_orchestrator().handle_command(command)
    if response is None:
        return {
            "accepted": True,
            "command_type": command.type,
            "chat_id": command.chat_id,
            "message_id": command.message_id,
        }
    return response
