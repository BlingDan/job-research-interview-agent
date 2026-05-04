from __future__ import annotations

import concurrent.futures
import json
import threading
import uuid
from datetime import datetime
from pathlib import Path

from app.agents.canvas_agent import build_canvas_artifact
from app.agents.doc_agent import build_doc_artifact
from app.agents.intent_router_agent import route_agent_pilot_message
from app.agents.planner_agent import build_agent_plan
from app.agents.presentation_agent import build_slide_artifact
from app.core.llm import JobResearchLLM
from app.agents.artifact_revision_agent import (
    ArtifactRevisionPatch,
    apply_canvas_patch,
    apply_doc_patch,
    apply_slides_patch,
    build_artifact_revision_patch,
    build_llm_revision_content,
)
from app.integrations.fake_lark_client import FakeLarkClient
from app.integrations.lark_client import LarkClient
from app.schemas.agent_pilot import (
    AgentPilotCommand,
    AgentPilotResponse,
    AgentPilotTask,
    ArtifactKind,
    ArtifactRef,
    RevisionRecord,
    TaskCreateRequest,
)
from app.services.artifact_brief_builder import build_artifact_brief
from app.services.delivery_service import (
    format_error_reply,
    format_final_reply,
    format_generating_card,
    format_help_reply,
    format_no_active_task_reply,
    format_plan_reply,
    format_progress_reply,
    format_reset_confirm_reply,
    format_reset_expired_reply,
    format_reset_reply,
    format_revision_clarification_reply,
    format_revision_reply,
    with_fallback_notice,
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
        background_auto_confirm: bool = False,
        tool_layer: FeishuToolLayer | None = None,
    ):
        self.state_service = state_service
        self.lark_client = lark_client
        self.stream_delay_seconds = max(stream_delay_seconds, 0.0)
        self.auto_confirm = auto_confirm
        self.background_auto_confirm = background_auto_confirm
        self.tool_layer = tool_layer or FeishuToolLayer(
            adapters={
                "mcp": FeishuMcpToolAdapter(mode="off"),
                "lark_cli": LarkCliToolAdapter(lark_client),
                "fake": LarkCliToolAdapter(FakeLarkClient()),
            }
        )

    def create_task(
        self, request: TaskCreateRequest, *, route_source: str | None = None
    ) -> AgentPilotResponse:
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
            reply = with_fallback_notice(format_plan_reply(task), route_source)
            self._send_or_reply(task, reply)
            if self.auto_confirm:
                self._send_or_reply(task, "已开始执行，正在并行生成 Doc、Slides 和 Canvas...")
                if self.background_auto_confirm:
                    self._start_background_confirm(task.task_id)
                    return self._response(task, format_progress_reply(task))
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

    def _start_background_confirm(self, task_id: str) -> None:
        thread = threading.Thread(
            target=self._run_confirmed_task_in_background,
            args=(task_id,),
            name=f"agent-pilot-confirm-{task_id}",
            daemon=True,
        )
        thread.start()

    def _run_confirmed_task_in_background(self, task_id: str) -> None:
        task: AgentPilotTask | None = None
        try:
            task = self.state_service.load_task(task_id)
            self._run_confirmed_task(task)
        except Exception as exc:
            if task is None:
                try:
                    task = self.state_service.load_task(task_id)
                except Exception:
                    return
            task.error = str(exc)
            self.state_service.update_status(task, "FAILED")
            reply = format_error_reply(task)
            self._send_or_reply(task, reply)

    def _run_confirmed_task(self, task: AgentPilotTask) -> AgentPilotResponse:
        if task.status == "DONE":
            reply = format_final_reply(task)
            self._send_or_reply(task, reply)
            return self._response(task, reply)

        task.artifacts = [
            item for item in task.artifacts if item.kind not in {"doc", "slides", "canvas"}
        ]
        task.tool_executions = []
        task.artifact_brief = build_artifact_brief(task)
        self.state_service.save_task(task)

        self.state_service.update_status(task, "GENERATING")
        card_id = self._send_generating_card(task)

        results = self._generate_artifacts_in_parallel(task, card_id)

        for artifact, records in results:
            task.artifacts.append(artifact)
            task.tool_executions.extend(records)

        self.state_service.save_task(task)
        self.state_service.update_status(task, "DELIVERING")

        reply = format_final_reply(task)
        if card_id:
            try:
                self.lark_client.update_message(card_id, reply)
            except Exception:
                self._send_or_reply(task, reply)
        else:
            self._send_or_reply(task, reply)

        self.state_service.update_status(task, "DONE")
        suggestion = self._generate_proactive_suggestion(task)
        if suggestion:
            self._send_or_reply(task, suggestion)
        return self._response(task, reply)

    def _send_generating_card(self, task: AgentPilotTask) -> str | None:
        statuses = {"doc": "生成中...", "slides": "生成中...", "canvas": "生成中..."}
        text = format_generating_card(statuses)
        try:
            result = self._send_or_reply_card_result(task, text, header_title="Agent-Pilot")
            return _message_id_from_result(result)
        except Exception:
            self._send_or_reply(task, text)
            return None

    def _generate_artifacts_in_parallel(
        self, task: AgentPilotTask, card_id: str | None
    ) -> list[tuple]:
        jobs = [
            ("create_doc", "Agent-Pilot 项目方案", build_doc_artifact(task)),
            ("create_slides", "Agent-Pilot 5 页汇报演示文稿", build_slide_artifact(task)),
            ("create_canvas", "Agent-Pilot 编排架构画板", build_canvas_artifact(task)),
        ]

        results: list[tuple] = []
        statuses: dict[str, str] = {"doc": "生成中...", "slides": "生成中...", "canvas": "生成中..."}
        lock = threading.Lock()

        with concurrent.futures.ThreadPoolExecutor(max_workers=3) as pool:
            futures = {
                pool.submit(
                    self._execute_artifact_isolated, task, capability, title, content
                ): capability
                for capability, title, content in jobs
            }
            for future in concurrent.futures.as_completed(futures):
                capability = futures[future]
                try:
                    artifact, records = future.result()
                    results.append((artifact, records))
                    kind = _capability_to_kind(capability)
                    with lock:
                        statuses[kind] = f"✅ 已完成 → {artifact.url or '已生成'}"
                except Exception:
                    kind = _capability_to_kind(capability)
                    with lock:
                        statuses[kind] = "⚠️ 生成失败，已使用备用链接"

                if card_id:
                    try:
                        card_text = format_generating_card(statuses)
                        self.lark_client.update_message(card_id, card_text)
                    except Exception:
                        pass

        return results

    def _execute_artifact_isolated(
        self,
        task: AgentPilotTask,
        capability: str,
        title: str,
        content: object,
    ) -> tuple:
        call = find_tool_call(task.plan.tool_plan if task.plan else None, capability)
        artifact, records = self.tool_layer.execute_artifact(
            call,
            task_id=task.task_id,
            title=title,
            content=content,
            task_dir=self.state_service.task_dir(task.task_id),
        )
        return artifact, records

    def get_task(self, task_id: str) -> AgentPilotResponse:
        task = self.state_service.load_task(task_id)
        return self._response(task, format_progress_reply(task))

    def get_progress(self, task_id: str) -> AgentPilotResponse:
        task = self.state_service.load_task(task_id)
        reply = format_progress_reply(task)
        self._send_or_reply(task, reply)
        return self._response(task, reply)

    def revise_task(
        self,
        task_id: str,
        instruction: str,
        *,
        target_artifacts: list[ArtifactKind] | None = None,
        needs_clarification: bool = False,
        route_reason: str = "",
        route_source: str | None = None,
    ) -> AgentPilotResponse:
        task = self.state_service.load_task(task_id)
        try:
            self.state_service.update_status(task, "REVISING")
            targets = target_artifacts if target_artifacts is not None else self._target_artifacts(instruction)
            if needs_clarification or not targets:
                self.state_service.update_status(task, "DONE")
                reply = with_fallback_notice(
                    format_revision_clarification_reply(task, instruction), route_source
                )
                self._send_or_reply(task, reply)
                return self._response(task, reply)

            used_fallback = False
            summaries: list[str] = []
            for target in targets:
                current = self._read_artifact_content(task, target)
                if current is None:
                    current = self._regenerate_content(task, target)

                rewritten, change_summary = None, ""
                try:
                    rewritten, change_summary = build_llm_revision_content(
                        instruction, current, target
                    )
                except Exception:
                    used_fallback = True

                if rewritten is not None:
                    try:
                        self._overwrite_artifact_content(task, target, rewritten)
                        summaries.append(change_summary or f"已重写 {target} 内容。")
                        continue
                    except Exception:
                        used_fallback = True

                patch = build_artifact_revision_patch(instruction, target)
                if patch.needs_clarification:
                    self.state_service.update_status(task, "DONE")
                    reply = with_fallback_notice(
                        format_revision_clarification_reply(task, instruction), route_source
                    )
                    self._send_or_reply(task, reply)
                    return self._response(task, reply)
                self._apply_single_patch(task, patch)
                summaries.append(_single_patch_summary(patch))

            effective_source = "fallback" if used_fallback else (route_source or "llm")
            revision = RevisionRecord(
                revision_id=str(uuid.uuid4()),
                instruction=instruction,
                target_artifacts=targets,
                summary=route_reason or "；".join(summaries),
            )
            task.revisions.append(revision)
            self.state_service.update_status(task, "DONE")
            reply = with_fallback_notice(format_revision_reply(task, revision), effective_source)
            self._send_or_reply(task, reply)
            return self._response(task, reply)
        except Exception as exc:
            task.error = str(exc)
            self.state_service.update_status(task, "FAILED")
            reply = format_error_reply(task)
            self._send_or_reply(task, reply)
            return self._response(task, reply)

    def _overwrite_artifact_content(
        self, task: AgentPilotTask, kind: ArtifactKind, content: str
    ) -> None:
        task_dir = self.state_service.task_dir(task.task_id)
        existing = _artifact_by_kind(task.artifacts, kind)
        if kind == "doc":
            artifact = self.lark_client.update_doc(task.task_id, existing, content, task_dir)
        elif kind == "slides":
            slides_data = json.loads(content)
            artifact = self.lark_client.update_slides(task.task_id, existing, slides_data, task_dir)
        else:
            artifact = self.lark_client.update_canvas(task.task_id, existing, content, task_dir)
        _replace_artifact(task, artifact)

    def _read_artifact_content(self, task: AgentPilotTask, kind: ArtifactKind) -> str | None:
        existing = _artifact_by_kind(task.artifacts, kind)
        if kind == "slides":
            slides = _read_slides_artifact(existing)
            if slides is None:
                return None
            return json.dumps(slides, ensure_ascii=False, indent=2)
        return _read_text_artifact(existing)

    def _regenerate_content(self, task: AgentPilotTask, kind: ArtifactKind) -> str:
        if kind == "doc":
            return build_doc_artifact(task)
        if kind == "slides":
            return json.dumps(build_slide_artifact(task), ensure_ascii=False, indent=2)
        return build_canvas_artifact(task)

    def _apply_single_patch(self, task: AgentPilotTask, patch: ArtifactRevisionPatch) -> None:
        task_dir = self.state_service.task_dir(task.task_id)
        existing = _artifact_by_kind(task.artifacts, patch.target_artifact)
        if patch.target_artifact == "doc":
            content = _read_text_artifact(existing) or build_doc_artifact(task)
            updated_content = apply_doc_patch(content, patch)
            if existing:
                artifact = self.lark_client.update_doc(task.task_id, existing, updated_content, task_dir)
            else:
                self._execute_artifact(task, "create_doc", "Agent-Pilot 项目方案", updated_content)
                return
        elif patch.target_artifact == "slides":
            slides = _read_slides_artifact(existing) or build_slide_artifact(task)
            updated_slides = apply_slides_patch(slides, patch)
            if existing:
                artifact = self.lark_client.update_slides(task.task_id, existing, updated_slides, task_dir)
            else:
                self._execute_artifact(task, "create_slides", "Agent-Pilot 5 页汇报演示文稿", updated_slides)
                return
        else:
            mermaid = _read_text_artifact(existing) or build_canvas_artifact(task)
            updated_mermaid = apply_canvas_patch(mermaid, patch)
            if existing:
                artifact = self.lark_client.update_canvas(task.task_id, existing, updated_mermaid, task_dir)
            else:
                self._execute_artifact(task, "create_canvas", "Agent-Pilot 编排架构画板", updated_mermaid)
                return
        _replace_artifact(task, artifact)

    def handle_command(self, command: AgentPilotCommand) -> AgentPilotResponse | None:
        if command.type == "help":
            self._send_command_reply(command, format_help_reply())
            return None
        if command.type == "reset":
            return self._handle_reset(command)
        if command.type == "confirm_reset":
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
                ),
                route_source=command.route_source,
            )
        if not command.chat_id and not command.task_id:
            return None
        task_id = command.task_id or self.state_service.get_active_task_id(command.chat_id or "")
        if not task_id:
            if command.type in {"confirm", "confirm_reset", "progress", "revise"}:
                self._send_command_reply(command, format_no_active_task_reply())
            return None
        if command.type == "confirm":
            return self.confirm_task(task_id)
        if command.type == "progress":
            return self.get_progress(task_id)
        if command.type == "revise":
            route_has_metadata = bool(
                command.target_artifacts
                or command.needs_clarification
                or command.route_confidence
                or command.route_reason
            )
            return self.revise_task(
                task_id,
                command.text,
                target_artifacts=command.target_artifacts if route_has_metadata else None,
                needs_clarification=command.needs_clarification,
                route_reason=command.route_reason,
                route_source=command.route_source,
            )
        return None

    def _handle_reset(self, command: AgentPilotCommand) -> AgentPilotResponse | None:
        if command.chat_id:
            task_id = self.state_service.get_active_task_id(command.chat_id)
            if task_id:
                task = self.state_service.load_task(task_id)
                if command.event_time is not None:
                    task_created = _parse_iso_to_float_s(task.created_at)
                    if task_created is not None and task_created > command.event_time:
                        self._send_command_reply(command, format_reset_expired_reply())
                        return None
                self._send_command_reply(command, format_reset_confirm_reply(task))
                return None
            self._send_command_reply(command, format_no_active_task_reply())
            return None
        self._send_command_reply(command, format_reset_reply())
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
            self._execute_artifact(task, "create_doc", "Agent-Pilot 项目方案", build_doc_artifact(task))
        if "slides" in targets:
            self._execute_artifact(task, "create_slides", "Agent-Pilot 5 页汇报演示文稿", build_slide_artifact(task))
        if "canvas" in targets:
            self._execute_artifact(task, "create_canvas", "Agent-Pilot 编排架构画板", build_canvas_artifact(task))
        self.state_service.save_task(task)

    def _apply_revision_patches(
        self, task: AgentPilotTask, patches: list[ArtifactRevisionPatch]
    ) -> None:
        task_dir = self.state_service.task_dir(task.task_id)
        for patch in patches:
            existing = _artifact_by_kind(task.artifacts, patch.target_artifact)
            if patch.target_artifact == "doc":
                content = _read_text_artifact(existing) or build_doc_artifact(task)
                updated_content = apply_doc_patch(content, patch)
                if existing:
                    artifact = self.lark_client.update_doc(
                        task.task_id, existing, updated_content, task_dir
                    )
                    _replace_artifact(task, artifact)
                else:
                    self._execute_artifact(
                        task,
                        "create_doc",
                        "Agent-Pilot 项目方案",
                        updated_content,
                    )
            elif patch.target_artifact == "slides":
                slides = _read_slides_artifact(existing) or build_slide_artifact(task)
                updated_slides = apply_slides_patch(slides, patch)
                if existing:
                    artifact = self.lark_client.update_slides(
                        task.task_id, existing, updated_slides, task_dir
                    )
                    _replace_artifact(task, artifact)
                else:
                    self._execute_artifact(
                        task,
                        "create_slides",
                        "Agent-Pilot 5 页汇报演示文稿",
                        updated_slides,
                    )
            else:
                mermaid = _read_text_artifact(existing) or build_canvas_artifact(task)
                updated_mermaid = apply_canvas_patch(mermaid, patch)
                if existing:
                    artifact = self.lark_client.update_canvas(
                        task.task_id, existing, updated_mermaid, task_dir
                    )
                    _replace_artifact(task, artifact)
                else:
                    self._execute_artifact(
                        task,
                        "create_canvas",
                        "Agent-Pilot 编排架构画板",
                        updated_mermaid,
                    )
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
        route = route_agent_pilot_message(instruction)
        return route.target_artifacts

    def _send_or_reply(self, task: AgentPilotTask, text: str) -> None:
        if task.message_id:
            self.lark_client.reply_message(task.message_id, text)
        elif task.chat_id:
            self.lark_client.send_message(task.chat_id, text)

    def _send_or_reply_card_result(self, task: AgentPilotTask, text: str, *, header_title: str | None = None) -> dict:
        if task.message_id:
            return self.lark_client.reply_interactive_card(task.message_id, text, header_title=header_title)
        if task.chat_id:
            return self.lark_client.send_interactive_card(task.chat_id, text, header_title=header_title)
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

    def _generate_proactive_suggestion(self, task: AgentPilotTask) -> str:
        try:
            summaries = "；".join(a.summary for a in task.artifacts if a.summary)
            if not summaries:
                return ""
            llm = JobResearchLLM(temperature=0.3, max_tokens=512)
            messages = [
                {
                    "role": "system",
                    "content": "你是 Agent-Pilot。根据刚刚完成的任务和产物，生成一条后续建议（1-2 句话）。例如：检测到方案中未涉及某方面，是否需要补充？如果不需要建议，返回空字符串。",
                },
                {
                    "role": "user",
                    "content": f"用户需求：{task.input_text}\n产物摘要：{summaries}\n请生成后续建议。",
                },
            ]
            result = llm.invoke(messages).strip()
            if len(result) < 5:
                return ""
            return f"\U0001F4AD {result}"
        except Exception:
            return ""


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


def _capability_to_kind(capability: str) -> str:
    if capability == "create_doc":
        return "doc"
    if capability == "create_slides":
        return "slides"
    return "canvas"


def _artifact_by_kind(
    artifacts: list[ArtifactRef], kind: ArtifactKind
) -> ArtifactRef | None:
    for artifact in artifacts:
        if artifact.kind == kind:
            return artifact
    return None


def _replace_artifact(task: AgentPilotTask, updated: ArtifactRef) -> None:
    for index, artifact in enumerate(task.artifacts):
        if artifact.kind == updated.kind:
            task.artifacts[index] = updated
            return
    task.artifacts.append(updated)


def _read_text_artifact(artifact: ArtifactRef | None) -> str | None:
    if not artifact or not artifact.local_path:
        return None
    path = Path(artifact.local_path)
    if not path.exists():
        return None
    return path.read_text(encoding="utf-8")


def _read_slides_artifact(artifact: ArtifactRef | None) -> list[dict[str, str]] | None:
    text = _read_text_artifact(artifact)
    if not text:
        return None
    try:
        value = json.loads(text)
    except json.JSONDecodeError:
        return None
    if not isinstance(value, list):
        return None
    slides: list[dict[str, str]] = []
    for item in value:
        if isinstance(item, dict):
            slides.append({str(key): str(value or "") for key, value in item.items()})
    return slides or None


def _single_patch_summary(patch: ArtifactRevisionPatch) -> str:
    return f"{patch.target_artifact}: {patch.operation} {patch.location}"


def _patch_summary(patches: list[ArtifactRevisionPatch]) -> str:
    details = [
        f"{patch.target_artifact}: {patch.operation} {patch.location}"
        for patch in patches
    ]
    return "已原地应用结构化修改补丁：" + "；".join(details)


def _parse_iso_to_float_s(iso_str: str) -> float | None:
    try:
        return datetime.fromisoformat(iso_str).timestamp()
    except (ValueError, TypeError):
        return None
