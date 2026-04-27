from __future__ import annotations

import time
import uuid

from app.agents.canvas_agent import build_canvas_artifact
from app.agents.doc_agent import build_doc_artifact
from app.agents.planner_agent import build_agent_plan
from app.agents.presentation_agent import build_slide_artifact
from app.integrations.fake_lark_client import FakeLarkClient
from app.integrations.lark_client import LarkClient
from app.schemas.agent_pilot import (
    AgentPilotCommand,
    AgentPilotResponse,
    AgentPilotTask,
    ArtifactKind,
    RevisionRecord,
    TaskCreateRequest,
)
from app.services.artifact_brief_builder import build_artifact_brief
from app.services.delivery_service import (
    format_error_reply,
    format_final_reply,
    format_help_reply,
    format_no_active_task_reply,
    format_plan_reply_chunks,
    format_plan_reply,
    format_planning_ack,
    format_progress_reply,
    format_reset_reply,
    format_revision_reply,
)
from app.services.feishu_tool_layer import FeishuMcpToolAdapter, FeishuToolLayer, LarkCliToolAdapter
from app.services.feishu_tool_registry import find_tool_call
from app.services.state_service import StateService


class AgentPilotOrchestrator:
    def __init__(
        self,
        state_service: StateService,
        lark_client: LarkClient,
        *,
        stream_delay_seconds: float = 0.0,
        auto_confirm: bool = False,
        tool_layer: FeishuToolLayer | None = None,
    ):
        self.state_service = state_service
        self.lark_client = lark_client
        self.stream_delay_seconds = max(stream_delay_seconds, 0.0)
        self.auto_confirm = auto_confirm
        self.tool_layer = tool_layer or FeishuToolLayer(
            adapters={
                "mcp": FeishuMcpToolAdapter(mode="off"),
                "lark_cli": LarkCliToolAdapter(lark_client),
                "fake": LarkCliToolAdapter(FakeLarkClient()),
            }
        )

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
            stream_message_id = self._send_planning_ack(task)
            task.plan = build_agent_plan(request.message)
            self.state_service.update_status(task, "WAITING_CONFIRMATION")
            reply = format_plan_reply(task)
            self._send_or_reply_stream(
                task,
                format_plan_reply_chunks(task),
                reply,
                stream_message_id=stream_message_id,
            )
            if self.auto_confirm:
                self._send_progress_update(
                    task,
                    "已进入自动执行模式，我会继续生成 Doc、Slides 和 Canvas，并在完成后把链接发回当前 IM。",
                )
                return self._run_confirmed_task(task)
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
            return self._run_confirmed_task(task)
        except Exception as exc:
            task.error = str(exc)
            self.state_service.update_status(task, "FAILED")
            reply = format_error_reply(task)
            self._send_or_reply(task, reply)
            return self._response(task, reply)

    def _run_confirmed_task(self, task: AgentPilotTask) -> AgentPilotResponse:
        if task.status == "DONE":
            reply = format_final_reply(task)
            return self._response(task, reply)

        task.artifacts = [
            item for item in task.artifacts if item.kind not in {"doc", "slides", "canvas"}
        ]
        task.tool_executions = []
        task.artifact_brief = build_artifact_brief(task)
        self.state_service.save_task(task)

        self.state_service.update_status(task, "DOC_GENERATING")
        self._send_progress_update(task, "Doc Agent 正在生成 Agent-Pilot 参赛方案文档。")
        doc = build_doc_artifact(task)
        self._execute_artifact(task, "create_doc", "Agent-Pilot 参赛方案", doc)
        self.state_service.save_task(task)

        self.state_service.update_status(task, "PRESENTATION_GENERATING")
        self._send_progress_update(task, "Presentation Agent 正在生成 5 页答辩汇报材料。")
        slides = build_slide_artifact(task)
        self._execute_artifact(task, "create_slides", "Agent-Pilot 5 页答辩汇报材料", slides)
        self.state_service.save_task(task)

        self.state_service.update_status(task, "CANVAS_GENERATING")
        self._send_progress_update(task, "Canvas Agent 正在生成飞书画板架构图。")
        canvas = build_canvas_artifact(task)
        self._execute_artifact(task, "create_canvas", "Agent-Pilot 编排架构画板", canvas)
        self.state_service.save_task(task)

        self.state_service.update_status(task, "DELIVERING")
        self._send_progress_update(task, "DeliveryService 正在汇总产物链接并回传到当前 IM。")
        reply = format_final_reply(task)
        self._send_or_reply(task, reply)
        self.state_service.update_status(task, "DONE")
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
            task.artifact_brief = build_artifact_brief(task)
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
        if command.type == "help":
            self._send_command_reply(command, format_help_reply())
            return None
        if command.type == "reset":
            if command.chat_id:
                self.state_service.clear_active_task(command.chat_id)
            self._send_command_reply(command, format_reset_reply())
            return None
        if command.type == "health":
            self._send_command_reply(command, "Agent-Pilot 在线。请直接发送办公协同任务，或回复「确认」「现在做到哪了？」「修改：...」。")
            return None
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
            if command.type in {"confirm", "progress", "revise"}:
                self._send_command_reply(command, format_no_active_task_reply())
            return None
        if command.type == "confirm":
            return self.confirm_task(task_id)
        if command.type == "progress":
            return self.get_progress(task_id)
        if command.type == "revise":
            return self.revise_task(task_id, command.text)
        return None

    def _send_command_reply(self, command: AgentPilotCommand, text: str) -> None:
        if command.message_id:
            self.lark_client.reply_message(command.message_id, text)
        elif command.chat_id:
            self.lark_client.send_message(command.chat_id, text)

    def _regenerate_targets(self, task: AgentPilotTask, targets: list[ArtifactKind]) -> None:
        task.artifacts = [artifact for artifact in task.artifacts if artifact.kind not in targets]
        target_call_ids = {
            find_tool_call(task.plan.tool_plan if task.plan else None, _capability_for_kind(kind)).id
            for kind in targets
        }
        task.tool_executions = [
            record for record in task.tool_executions if record.call_id not in target_call_ids
        ]
        if "doc" in targets:
            self._execute_artifact(task, "create_doc", "Agent-Pilot 参赛方案", build_doc_artifact(task))
        if "slides" in targets:
            self._execute_artifact(task, "create_slides", "Agent-Pilot 5 页答辩汇报材料", build_slide_artifact(task))
        if "canvas" in targets:
            self._execute_artifact(task, "create_canvas", "Agent-Pilot 编排架构画板", build_canvas_artifact(task))
        self.state_service.save_task(task)

    def _execute_artifact(
        self,
        task: AgentPilotTask,
        capability: str,
        title: str,
        content: object,
    ) -> None:
        call = find_tool_call(task.plan.tool_plan if task.plan else None, capability)
        artifact, records = self.tool_layer.execute_artifact(
            call,
            task_id=task.task_id,
            title=title,
            content=content,
            task_dir=self.state_service.task_dir(task.task_id),
        )
        task.artifacts.append(artifact)
        task.tool_executions.extend(records)

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

    def _send_progress_update(self, task: AgentPilotTask, text: str) -> None:
        try:
            self._send_or_reply(task, text)
        except Exception:
            pass

    def _send_planning_ack(self, task: AgentPilotTask) -> str | None:
        try:
            result = self._send_or_reply_card_result(task, format_planning_ack())
        except Exception:
            self._send_or_reply(task, format_planning_ack())
            return None
        return _message_id_from_result(result)

    def _send_or_reply_stream(
        self,
        task: AgentPilotTask,
        chunks: list[str],
        final_text: str,
        *,
        stream_message_id: str | None = None,
    ) -> None:
        if stream_message_id:
            try:
                stream_chunks = chunks[1:] if len(chunks) > 1 else [final_text]
                for chunk in stream_chunks:
                    if self.stream_delay_seconds:
                        time.sleep(self.stream_delay_seconds)
                    self.lark_client.update_message(stream_message_id, chunk)
                return
            except Exception:
                self._send_or_reply(task, final_text)
                return

        if len(chunks) < 2:
            self._send_or_reply(task, final_text)
            return

        try:
            result = self._send_or_reply_card_result(task, chunks[0])
        except Exception:
            self._send_or_reply(task, final_text)
            return

        stream_message_id = _message_id_from_result(result)
        if not stream_message_id:
            self._send_or_reply(task, final_text)
            return

        try:
            for chunk in chunks[1:]:
                if self.stream_delay_seconds:
                    time.sleep(self.stream_delay_seconds)
                self.lark_client.update_message(stream_message_id, chunk)
        except Exception:
            self._send_or_reply(task, final_text)

    def _send_or_reply_card_result(self, task: AgentPilotTask, text: str) -> dict:
        if task.message_id:
            return self.lark_client.reply_interactive_card(task.message_id, text)
        if task.chat_id:
            return self.lark_client.send_interactive_card(task.chat_id, text)
        return {}

    def _response(self, task: AgentPilotTask, reply: str) -> AgentPilotResponse:
        return AgentPilotResponse(
            task_id=task.task_id,
            status=task.status,
            plan=task.plan,
            artifact_brief=task.artifact_brief,
            artifacts=task.artifacts,
            tool_executions=task.tool_executions,
            revisions=task.revisions,
            reply=reply,
            error=task.error,
        )


def _message_id_from_result(result: dict) -> str | None:
    message_id = result.get("message_id")
    if isinstance(message_id, str) and message_id:
        return message_id

    data = result.get("data")
    if isinstance(data, dict):
        message_id = data.get("message_id")
        if isinstance(message_id, str) and message_id:
            return message_id

    return None


def _capability_for_kind(kind: ArtifactKind) -> str:
    if kind == "doc":
        return "create_doc"
    if kind == "slides":
        return "create_slides"
    return "create_canvas"
