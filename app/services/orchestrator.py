from __future__ import annotations

import uuid

from app.agents.canvas_agent import build_canvas_artifact
from app.agents.doc_agent import build_doc_artifact
from app.agents.planner_agent import build_agent_plan
from app.agents.presentation_agent import build_slide_artifact
from app.integrations.lark_client import LarkClient
from app.schemas.agent_pilot import (
    AgentPilotCommand,
    AgentPilotResponse,
    AgentPilotTask,
    ArtifactKind,
    RevisionRecord,
    TaskCreateRequest,
)
from app.services.delivery_service import (
    format_error_reply,
    format_final_reply,
    format_plan_reply,
    format_progress_reply,
    format_revision_reply,
)
from app.services.state_service import StateService


class AgentPilotOrchestrator:
    def __init__(self, state_service: StateService, lark_client: LarkClient):
        self.state_service = state_service
        self.lark_client = lark_client

    def create_task(self, request: TaskCreateRequest) -> AgentPilotResponse:
        task = AgentPilotTask(
            task_id=str(uuid.uuid4()),
            input_text=request.message,
            chat_id=request.chat_id,
            message_id=request.message_id,
            user_id=request.user_id,
            status="CREATED",
        )
        try:
            self.state_service.update_status(task, "PLANNING")
            task.plan = build_agent_plan(request.message)
            self.state_service.update_status(task, "WAITING_CONFIRMATION")
            reply = format_plan_reply(task)
            self._send_or_reply(task, reply)
            return self._response(task, reply)
        except Exception as exc:
            task.error = str(exc)
            self.state_service.update_status(task, "FAILED")
            reply = format_error_reply(task)
            self._send_or_reply(task, reply)
            return self._response(task, reply)

    def confirm_task(self, task_id: str) -> AgentPilotResponse:
        task = self.state_service.load_task(task_id)
        try:
            if task.status == "DONE":
                reply = format_final_reply(task)
                return self._response(task, reply)
            task.artifacts = [item for item in task.artifacts if item.kind not in {"doc", "slides", "canvas"}]

            self.state_service.update_status(task, "DOC_GENERATING")
            doc = build_doc_artifact(task)
            task.artifacts.append(
                self.lark_client.create_doc(
                    task.task_id,
                    "Agent-Pilot 参赛方案",
                    doc,
                    self.state_service.task_dir(task.task_id),
                )
            )
            self.state_service.save_task(task)

            self.state_service.update_status(task, "PRESENTATION_GENERATING")
            slides = build_slide_artifact(task)
            task.artifacts.append(
                self.lark_client.create_slides(
                    task.task_id,
                    "Agent-Pilot 5 页答辩汇报材料",
                    slides,
                    self.state_service.task_dir(task.task_id),
                )
            )
            self.state_service.save_task(task)

            self.state_service.update_status(task, "CANVAS_GENERATING")
            canvas = build_canvas_artifact(task)
            task.artifacts.append(
                self.lark_client.create_canvas(
                    task.task_id,
                    "Agent-Pilot 编排架构画板",
                    canvas,
                    self.state_service.task_dir(task.task_id),
                )
            )
            self.state_service.save_task(task)

            self.state_service.update_status(task, "DELIVERING")
            reply = format_final_reply(task)
            self._send_or_reply(task, reply)
            self.state_service.update_status(task, "DONE")
            return self._response(task, reply)
        except Exception as exc:
            task.error = str(exc)
            self.state_service.update_status(task, "FAILED")
            reply = format_error_reply(task)
            self._send_or_reply(task, reply)
            return self._response(task, reply)

    def get_task(self, task_id: str) -> AgentPilotResponse:
        task = self.state_service.load_task(task_id)
        return self._response(task, format_progress_reply(task))

    def get_progress(self, task_id: str) -> AgentPilotResponse:
        task = self.state_service.load_task(task_id)
        reply = format_progress_reply(task)
        self._send_or_reply(task, reply)
        return self._response(task, reply)

    def revise_task(self, task_id: str, instruction: str) -> AgentPilotResponse:
        task = self.state_service.load_task(task_id)
        try:
            self.state_service.update_status(task, "REVISING")
            targets = self._target_artifacts(instruction)
            revision = RevisionRecord(
                revision_id=str(uuid.uuid4()),
                instruction=instruction,
                target_artifacts=targets,
                summary="已根据修改意见重新生成相关产物。",
            )
            task.revisions.append(revision)
            self._regenerate_targets(task, targets)
            self.state_service.update_status(task, "DONE")
            reply = format_revision_reply(task, revision)
            self._send_or_reply(task, reply)
            return self._response(task, reply)
        except Exception as exc:
            task.error = str(exc)
            self.state_service.update_status(task, "FAILED")
            reply = format_error_reply(task)
            self._send_or_reply(task, reply)
            return self._response(task, reply)

    def handle_command(self, command: AgentPilotCommand) -> AgentPilotResponse | None:
        if command.type == "new_task":
            return self.create_task(
                TaskCreateRequest(
                    message=command.text,
                    chat_id=command.chat_id,
                    message_id=command.message_id,
                    user_id=command.user_id,
                )
            )
        if not command.chat_id and not command.task_id:
            return None
        task_id = command.task_id or self.state_service.get_active_task_id(command.chat_id or "")
        if not task_id:
            return None
        if command.type == "confirm":
            return self.confirm_task(task_id)
        if command.type == "progress":
            return self.get_progress(task_id)
        if command.type == "revise":
            return self.revise_task(task_id, command.text)
        return None

    def _regenerate_targets(self, task: AgentPilotTask, targets: list[ArtifactKind]) -> None:
        task.artifacts = [artifact for artifact in task.artifacts if artifact.kind not in targets]
        task_dir = self.state_service.task_dir(task.task_id)
        if "doc" in targets:
            task.artifacts.append(
                self.lark_client.create_doc(
                    task.task_id,
                    "Agent-Pilot 参赛方案",
                    build_doc_artifact(task),
                    task_dir,
                )
            )
        if "slides" in targets:
            task.artifacts.append(
                self.lark_client.create_slides(
                    task.task_id,
                    "Agent-Pilot 5 页答辩汇报材料",
                    build_slide_artifact(task),
                    task_dir,
                )
            )
        if "canvas" in targets:
            task.artifacts.append(
                self.lark_client.create_canvas(
                    task.task_id,
                    "Agent-Pilot 编排架构画板",
                    build_canvas_artifact(task),
                    task_dir,
                )
            )
        self.state_service.save_task(task)

    def _target_artifacts(self, instruction: str) -> list[ArtifactKind]:
        text = instruction.lower()
        targets: list[ArtifactKind] = []
        if any(key in text for key in ["doc", "文档", "方案"]):
            targets.append("doc")
        if any(key in text for key in ["ppt", "slides", "汇报", "答辩", "演示"]):
            targets.append("slides")
        if any(key in text for key in ["canvas", "whiteboard", "画板", "架构图", "流程图"]):
            targets.append("canvas")
        return targets or ["doc", "slides", "canvas"]

    def _send_or_reply(self, task: AgentPilotTask, text: str) -> None:
        if task.message_id:
            self.lark_client.reply_message(task.message_id, text)
        elif task.chat_id:
            self.lark_client.send_message(task.chat_id, text)

    def _response(self, task: AgentPilotTask, reply: str) -> AgentPilotResponse:
        return AgentPilotResponse(
            task_id=task.task_id,
            status=task.status,
            plan=task.plan,
            artifacts=task.artifacts,
            revisions=task.revisions,
            reply=reply,
            error=task.error,
        )

