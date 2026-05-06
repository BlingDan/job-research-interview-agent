from __future__ import annotations

import concurrent.futures
import json
import threading
import time
import uuid
from datetime import datetime
from pathlib import Path

from app.agents.canvas_agent import build_canvas_artifact
from app.agents.doc_agent import build_doc_artifact
from app.agents.intent_router_agent import route_agent_pilot_message
from app.agents.agent_pilot_planner import build_agent_plan
from app.agents.presentation_agent import build_slide_artifact
from app.core.config import get_settings
from app.core.llm import JobResearchLLM
from app.core.logging import get_logger
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
    ChatMessage,
    FeedbackRecord,
    RevisionRecord,
    TaskCreateRequest,
)
from app.services.artifact_brief_builder import build_artifact_brief
from app.services.delivery_service import (
    format_auto_execute_reply,
    format_clarification_reply,
    format_countdown_expired_reply,
    format_countdown_reply,
    format_error_reply,
    format_feedback_prompt,
    format_feedback_thanks,
    format_final_reply,
    format_generating_card,
    format_help_reply,
    format_no_active_task_reply,
    format_plan_reply,
    format_progress_reply,
    format_rehearse_reply,
    format_reset_confirm_reply,
    format_reset_expired_reply,
    format_reset_reply,
    format_revision_clarification_reply,
    format_revision_reply,
    with_fallback_notice,
)
from app.services.feishu_tool_layer import FeishuMcpToolAdapter, FeishuToolLayer, LarkCliToolAdapter
from app.services.feishu_tool_registry import find_tool_call
from app.shared.state_service import DbStateService

logger = get_logger()


class AgentPilotOrchestrator:
    def __init__(
        self,
        state_service: DbStateService,
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
        self._countdown_timers: dict[str, threading.Timer] = {}

    def create_task(
        self, request: TaskCreateRequest, *, route_source: str | None = None
    ) -> AgentPilotResponse:
        t0 = time.monotonic()
        task = AgentPilotTask(
            task_id=str(uuid.uuid4()),
            input_text=request.message,
            chat_id=request.chat_id,
            message_id=request.message_id,
            user_id=request.user_id,
            status="CREATED",
        )
        logger.info("Task created (task_id=%s, chat_id=%s).", task.task_id, task.chat_id)
        try:
            self.state_service.update_status(task, "PLANNING")

            t1 = time.monotonic()
            chat_history = self._fetch_chat_context(request)
            t2 = time.monotonic()
            task.plan = build_agent_plan(request.message, chat_history)
            t3 = time.monotonic()
            logger.info(
                "Task plan built (task_id=%s, chat_context=%.1fs, plan=%.1fs).",
                task.task_id,
                t2 - t1,
                t3 - t2,
            )

            settings = get_settings()
            high_threshold = settings.agent_pilot_confidence_high_threshold
            medium_threshold = settings.agent_pilot_confidence_medium_threshold

            if self.auto_confirm:
                self.state_service.update_status(task, "GENERATING")
                self._send_or_reply(task, "已开始执行，正在并行生成 Doc、Slides 和 Canvas...")
                if self.background_auto_confirm:
                    self._start_background_confirm(task.task_id)
                    return self._response(task, format_progress_reply(task))
                return self._run_confirmed_task(task)

            if task.plan.clarification_questions:
                self.state_service.update_status(task, "WAITING_CONFIRMATION")
                reply = with_fallback_notice(
                    format_clarification_reply(task), route_source
                )
                self._send_or_reply(task, reply)
                return self._response(task, reply)

            if task.plan.confidence > high_threshold:
                self.state_service.update_status(task, "GENERATING")
                reply = with_fallback_notice(
                    format_auto_execute_reply(task), route_source
                )
                self._send_or_reply(task, reply)
                return self._run_confirmed_task(task)

            if task.plan.confidence >= medium_threshold:
                self.state_service.update_status(task, "WAITING_CONFIRMATION")
                countdown = settings.agent_pilot_countdown_seconds
                reply = with_fallback_notice(
                    format_countdown_reply(task, countdown), route_source
                )
                self._send_or_reply(task, reply)
                self._start_background_countdown(task.task_id, countdown)
                return self._response(task, reply)

            self.state_service.update_status(task, "WAITING_CONFIRMATION")
            reply = with_fallback_notice(format_plan_reply(task), route_source)
            self._send_or_reply(task, reply)
            return self._response(task, reply)
        except Exception as exc:
            logger.error(
                "Task creation failed (task_id=%s, elapsed=%.1fs): %s",
                task.task_id,
                time.monotonic() - t0,
                exc,
                exc_info=True,
            )
            task.error = str(exc)
            self.state_service.update_status(task, "FAILED")
            reply = format_error_reply(task)
            self._send_or_reply(task, reply)
            return self._response(task, reply)

    def handle_clarification(self, task_id: str, answer: str) -> AgentPilotResponse:
        task = self.state_service.load_task(task_id)
        try:
            combined = f"{task.input_text}\n（补充说明：{answer}）"
            task.plan = build_agent_plan(combined)
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

    def handle_feedback(
        self, task_id: str, rating: str, comment: str = ""
    ) -> AgentPilotResponse:
        task = self.state_service.load_task(task_id)
        feedback = FeedbackRecord(
            feedback_id=str(uuid.uuid4()),
            task_id=task_id,
            rating=rating if rating in {"helpful", "needs_improvement"} else None,
            comment=comment,
        )
        logger.info(
            "Feedback received (task_id=%s, rating=%s).", task_id, rating
        )
        reply = format_feedback_thanks(rating)
        self._send_or_reply(task, reply)
        return self._response(task, reply)

    def handle_rehearse(self, task_id: str) -> AgentPilotResponse:
        task = self.state_service.load_task(task_id)
        try:
            slides_artifact = _artifact_by_kind(task.artifacts, "slides")
            doc_artifact = _artifact_by_kind(task.artifacts, "doc")

            doc_content = _read_text_artifact(doc_artifact) or ""
            if len(doc_content) > 3000:
                doc_content = doc_content[:3000]

            llm = JobResearchLLM(temperature=0.7, max_tokens=1024)
            messages = [
                {
                    "role": "system",
                    "content": (
                        "你是方案评审专家。基于提供的方案文档和 Slides 内容，扮演评委/老板/客户角色，"
                        "提出 2-3 个尖锐但有价值的质疑问题。每个问题应针对方案中的潜在弱点、"
                        "逻辑漏洞或未充分考虑的风险。问题要有建设性，帮助方案完善。"
                    ),
                },
                {
                    "role": "user",
                    "content": f"方案文档摘要：{doc_content}\n请提出评审问题。",
                },
            ]
            questions_text = llm.invoke(messages).strip()

            reply = format_rehearse_reply(questions_text)
            self._send_or_reply(task, reply)
            return self._response(task, reply)
        except Exception as exc:
            logger.error("Rehearse failed (task_id=%s): %s", task_id, exc, exc_info=True)
            task.error = str(exc)
            self.state_service.update_status(task, "FAILED")
            reply = format_error_reply(task)
            self._send_or_reply(task, reply)
            return self._response(task, reply)

    def confirm_task(self, task_id: str) -> AgentPilotResponse:
        task = self.state_service.load_task(task_id)
        try:
            timer = self._countdown_timers.pop(task_id, None)
            if timer is not None:
                timer.cancel()
            return self._run_confirmed_task(task)
        except Exception as exc:
            task.error = str(exc)
            self.state_service.update_status(task, "FAILED")
            reply = format_error_reply(task)
            self._send_or_reply(task, reply)
            return self._response(task, reply)

    def _start_background_countdown(self, task_id: str, seconds: int) -> None:
        timer = threading.Timer(seconds, self._on_countdown_expired, args=(task_id,))
        timer.daemon = True
        self._countdown_timers[task_id] = timer
        timer.start()

    def _on_countdown_expired(self, task_id: str) -> None:
        self._countdown_timers.pop(task_id, None)
        try:
            task = self.state_service.load_task(task_id)
            if task.status == "WAITING_CONFIRMATION":
                self._send_or_reply(task, format_countdown_expired_reply())
                self._run_confirmed_task(task)
        except Exception as exc:
            logger.error("Countdown auto-confirm failed (task_id=%s): %s", task_id, exc, exc_info=True)

    def _fetch_chat_context(
        self, request: TaskCreateRequest
    ) -> list[ChatMessage]:
        if not request.chat_id:
            return list(request.chat_history)
        settings = get_settings()
        limit = settings.agent_pilot_chat_context_limit
        chat_timeout = getattr(settings, "agent_pilot_chat_context_timeout_seconds", 5.0)
        try:
            with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
                future = pool.submit(self.lark_client.fetch_recent_messages, request.chat_id, limit)
                raw_messages = future.result(timeout=chat_timeout)
        except concurrent.futures.TimeoutError:
            logger.warning("Chat context fetch timed out after %.1fs for chat_id=%s.", chat_timeout, request.chat_id)
            return list(request.chat_history) if request.chat_history else []
        except Exception:
            logger.debug("Failed to fetch chat context for chat_id=%s.", request.chat_id, exc_info=True)
            return list(request.chat_history) if request.chat_history else []

        fetched: list[ChatMessage] = []
        try:
            for msg in raw_messages:
                fetched.append(
                    ChatMessage(
                        sender_name=str(msg.get("sender_name", "")),
                        content=str(msg.get("content", "")),
                        timestamp=msg.get("timestamp"),
                    )
                )
        except Exception:
            logger.debug("Failed to parse chat context for chat_id=%s.", request.chat_id, exc_info=True)
            return list(request.chat_history) if request.chat_history else []

        if not fetched and request.chat_history:
            return list(request.chat_history)
        return fetched

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

        logger.info("Task confirmed, generating artifacts (task_id=%s).", task.task_id)
        self.state_service.update_status(task, "GENERATING")
        card_id = self._send_generating_card(task)

        results = self._generate_artifacts_in_parallel(task, card_id)

        for artifact, records in results:
            task.artifacts.append(artifact)
            task.tool_executions.extend(records)

        self.state_service.save_task(task)
        self.state_service.update_status(task, "DELIVERING")

        settings = get_settings()
        reply = format_final_reply(task, product_mode=settings.agent_pilot_product_mode)
        if card_id:
            try:
                self.lark_client.update_message(card_id, reply)
            except Exception:
                self._send_or_reply(task, reply)
        else:
            self._send_or_reply(task, reply)

        self.state_service.update_status(task, "DONE")
        logger.info("Task delivered (task_id=%s).", task.task_id)
        suggestion = self._generate_proactive_suggestion(task)
        if suggestion:
            self._send_or_reply(task, suggestion)

        self._send_or_reply(task, format_feedback_prompt())

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
        product_mode = get_settings().agent_pilot_product_mode
        doc_title = _dynamic_doc_title(task) if product_mode else "Agent-Pilot 项目方案"
        slides_title = _dynamic_slides_title(task) if product_mode else "Agent-Pilot 汇报演示文稿"

        jobs = [
            ("create_doc", doc_title, build_doc_artifact(task)),
            ("create_slides", slides_title, build_slide_artifact(task)),
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
            change_details: list[str] = []
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
                        change_details.append(
                            _build_change_detail(target, instruction, change_summary)
                        )
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
                    return self._response(task, patch)
                self._apply_single_patch(task, patch)
                summaries.append(_single_patch_summary(patch))
                change_details.append(
                    f"{target}: {patch.operation} {patch.location}"
                )

            effective_source = "fallback" if used_fallback else (route_source or "llm")
            combined_detail = "\n".join(change_details) if change_details else ""
            revision = RevisionRecord(
                revision_id=str(uuid.uuid4()),
                instruction=instruction,
                target_artifacts=targets,
                summary=route_reason or "；".join(summaries),
                change_detail=combined_detail,
            )
            task.revisions.append(revision)
            self.state_service.update_status(task, "DONE")
            reply = with_fallback_notice(
                format_revision_reply(task, revision), effective_source
            )
            self._send_or_reply(task, reply)
            return self._response(task, reply)
        except Exception as exc:
            logger.error("Revision failed (task_id=%s): %s", task_id, exc, exc_info=True)
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
                self._execute_artifact(task, "create_slides", "Agent-Pilot 汇报演示文稿", updated_slides)
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
        if command.type == "chat":
            self._send_command_reply(command, "收到。如需生成文档、PPT 或画板，请直接描述你的任务。回复「帮助」查看可用命令。")
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
            if command.type in {"confirm", "confirm_reset", "progress", "revise", "clarify", "feedback", "rehearse"}:
                self._send_command_reply(command, format_no_active_task_reply())
            return None
        if command.type == "confirm":
            return self.confirm_task(task_id)
        if command.type == "progress":
            return self.get_progress(task_id)
        if command.type == "clarify":
            return self.handle_clarification(task_id, command.text)
        if command.type == "feedback":
            return self.handle_feedback(task_id, command.text)
        if command.type == "rehearse":
            return self.handle_rehearse(task_id)
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
            self._execute_artifact(task, "create_slides", "Agent-Pilot 汇报演示文稿", build_slide_artifact(task))
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
                        "Agent-Pilot 汇报演示文稿",
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
                    "content": (
                        "你是 Agent-Pilot。根据刚刚完成的任务和产物，生成一条有洞察力的后续建议（2-3 句话）。"
                        "例如：检测到方案中未涉及某方面，是否需要补充？发现某个风险点需要进一步讨论？"
                        "如果不需要建议，返回空字符串。建议应具体、可操作。"
                    ),
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
            logger.debug("Failed to generate proactive suggestion (task_id=%s).", task.task_id, exc_info=True)
            return ""


def _dynamic_doc_title(task: AgentPilotTask) -> str:
    if task.plan and task.plan.summary:
        short = task.plan.summary.split("。")[0][:40]
        return short if short else "方案文档"
    return f"方案文档 - {task.input_text[:30]}"


def _dynamic_slides_title(task: AgentPilotTask) -> str:
    if task.plan and task.plan.summary:
        short = task.plan.summary.split("。")[0][:30]
        return f"{short} - 汇报演示" if short else "汇报演示文稿"
    return "汇报演示文稿"


def _build_change_detail(target: str, instruction: str, summary: str) -> str:
    label = {"doc": "文档", "slides": "Slides", "canvas": "Canvas"}.get(target, target)
    summary_text = summary or f"已按「{instruction[:30]}...」重写内容"
    return f"{label}: {summary_text}"


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


