from __future__ import annotations

import concurrent.futures
import json
import re
from textwrap import dedent
from typing import Any

from app.core.config import get_settings
from app.core.llm import JobResearchLLM
from app.schemas.agent_pilot import ArtifactKind, IntentRoute, MessageCommandType


REVISION_PREFIXES = ("修改：", "修改:", "调整：", "调整:", "更新：", "更新:")
EDIT_ACTION_KEYWORDS = (
    "修改",
    "调整",
    "更新",
    "添加",
    "增加",
    "删除",
    "移除",
    "替换",
    "插入",
    "改成",
    "改为",
    "加上",
    "删掉",
)
DOC_KEYWORDS = ("doc", "文档", "方案", "参赛方案")
DOC_LOCATION_HINT_KEYWORDS = (
    "最后一行",
    "文末",
    "末尾",
    "开头",
    "第一行",
    "正文",
    "段落",
    "章节",
    "小节",
)
SLIDES_KEYWORDS = (
    "ppt",
    "slides",
    "slide",
    "幻灯片",
    "汇报",
    "答辩",
    "演示",
    "第1页",
    "第 1 页",
    "页面",
)
CANVAS_KEYWORDS = (
    "canvas",
    "whiteboard",
    "画板",
    "白板",
    "架构图",
    "流程图",
)

_COMMAND_TYPES: set[str] = {
    "new_task",
    "confirm",
    "confirm_reset",
    "progress",
    "revise",
    "health",
    "help",
    "reset",
    "unknown",
}
_ARTIFACT_KINDS: set[str] = {"doc", "slides", "canvas"}


INTENT_ROUTER_SYSTEM_PROMPT = dedent(
    """
    你是 Agent-Pilot 的 Intent Router Agent。
    你的任务是把飞书 IM 文本路由成一个安全、结构化的执行决策。

    只返回 JSON 对象，不要 Markdown。字段：
    - command_type: new_task / confirm / progress / revise / health / help / reset / unknown
    - target_artifacts: doc、slides、canvas 的数组；只有 revise 才需要
    - confidence: 0 到 1
    - needs_clarification: true/false
    - reason: 简短说明

    规则：
    1. 「确认」「现在做到哪了？」「/help」「/reset」等硬命令要直接分类。
    2. 对已有产物的自然语言编辑属于 revise，即使没有「修改：」前缀。
    3. 用户提到文档、方案、参赛方案、最后一行、文末、段落、正文，通常指向 doc。
    4. 用户提到 PPT、Slides、幻灯片、汇报材料、答辩页，通常指向 slides。
    5. 用户提到 Canvas、画板、白板、架构图、流程图、节点、连线，通常指向 canvas。
    6. 不要因为修改请求含糊就默认 target_artifacts 为 doc/slides/canvas 全部。
       如果无法判断目标产物，target_artifacts 为空并 needs_clarification=true。
    """
).strip()


def _router_timeout() -> float:
    return float(getattr(get_settings(), "agent_pilot_router_timeout_seconds", 15.0))


def route_agent_pilot_message(text: str) -> IntentRoute:
    normalized = _strip_bot_mention(text)
    command_route = _route_hard_command(normalized)
    if command_route:
        return command_route

    mode = getattr(get_settings(), "agent_pilot_router_mode", "auto")
    if mode != "fallback":
        try:
            return _build_llm_intent_route_with_timeout(normalized)
        except Exception:
            if mode == "llm":
                raise

    return build_fallback_intent_route(normalized)


def _build_llm_intent_route_with_timeout(text: str) -> IntentRoute:
    with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
        future = pool.submit(build_llm_intent_route, text)
        return future.result(timeout=_router_timeout())


def build_llm_intent_route(text: str) -> IntentRoute:
    llm = JobResearchLLM(temperature=0.0, max_tokens=512)
    messages = [
        {"role": "system", "content": INTENT_ROUTER_SYSTEM_PROMPT},
        {"role": "user", "content": f"飞书 IM 文本：\n{text}"},
    ]
    route = parse_intent_route_output(llm.invoke(messages).strip(), text=text)
    route.route_source = "llm"
    return route


def build_fallback_intent_route(text: str) -> IntentRoute:
    normalized = _strip_bot_mention(text)
    command_route = _route_hard_command(normalized)
    if command_route:
        return command_route

    targets = infer_revision_targets(normalized)
    has_revision_prefix = normalized.startswith(REVISION_PREFIXES)
    has_edit_action = _contains_any(normalized, normalized.lower(), EDIT_ACTION_KEYWORDS)

    if has_revision_prefix or (has_edit_action and targets):
        return IntentRoute(
            command_type="revise",
            text=normalized,
            target_artifacts=targets,
            confidence=0.95 if targets else 0.45,
            needs_clarification=not targets,
            reason=(
                "命中修改语义并识别出目标产物。"
                if targets
                else "命中修改语义，但目标产物不明确。"
            ),
            route_source="fallback",
        )

    return IntentRoute(
        command_type="new_task",
        text=normalized,
        confidence=0.75,
        reason="未命中硬命令或既有产物修改语义，按新任务处理。",
        route_source="fallback",
    )


def parse_intent_route_output(raw_text: str, *, text: str = "") -> IntentRoute:
    data = _extract_json_object(raw_text)
    command_type = str(data.get("command_type") or "unknown").strip()
    if command_type not in _COMMAND_TYPES:
        command_type = "unknown"

    target_artifacts = [
        item
        for item in data.get("target_artifacts", [])
        if isinstance(item, str) and item in _ARTIFACT_KINDS
    ]
    confidence = _bounded_float(data.get("confidence"), default=0.0)
    needs_clarification = bool(data.get("needs_clarification", False))
    if command_type == "revise" and not target_artifacts:
        needs_clarification = True

    return IntentRoute(
        command_type=command_type,  # type: ignore[arg-type]
        text=text,
        target_artifacts=target_artifacts,  # type: ignore[arg-type]
        confidence=confidence,
        needs_clarification=needs_clarification,
        reason=str(data.get("reason") or "").strip(),
    )


def infer_revision_targets(text: str) -> list[ArtifactKind]:
    lower = text.lower()
    targets: list[ArtifactKind] = []

    if _contains_any(text, lower, DOC_KEYWORDS) or _contains_any(
        text, lower, DOC_LOCATION_HINT_KEYWORDS
    ):
        targets.append("doc")
    if _contains_any(text, lower, SLIDES_KEYWORDS):
        targets.append("slides")
    if _contains_any(text, lower, CANVAS_KEYWORDS):
        targets.append("canvas")

    return targets


def _route_hard_command(text: str) -> IntentRoute | None:
    normalized = text.strip()
    lower = normalized.lower()

    if not normalized:
        return IntentRoute(command_type="unknown", text=normalized, confidence=1.0, route_source="hard_command")
    if lower in {"/help", "help", "帮助", "命令"}:
        return IntentRoute(command_type="help", text=normalized, confidence=1.0, route_source="hard_command")
    if lower in {"/reset", "reset", "重置", "清空上下文"}:
        return IntentRoute(command_type="reset", text=normalized, confidence=1.0, route_source="hard_command")
    if lower in {"ping", "/ping", "hello", "hi"} or normalized in {"你好", "在吗"}:
        return IntentRoute(command_type="health", text=normalized, confidence=1.0, route_source="hard_command")
    if normalized == "确认":
        return IntentRoute(command_type="confirm", text=normalized, confidence=1.0, route_source="hard_command")
    if normalized == "确认重置":
        return IntentRoute(command_type="confirm_reset", text=normalized, confidence=1.0, route_source="hard_command")
    if lower in {"/status", "status"} or normalized in {
        "现在做到哪了？",
        "现在做到哪了?",
        "进度",
        "当前进度",
        "状态",
    }:
        return IntentRoute(command_type="progress", text=normalized, confidence=1.0, route_source="hard_command")
    return None


def _strip_bot_mention(text: str) -> str:
    stripped = (text or "").strip()
    stripped = re.sub(r"^@Agent\s*", "", stripped, flags=re.IGNORECASE)
    return stripped.strip()


def _contains_any(text: str, lower: str, keywords: tuple[str, ...]) -> bool:
    return any(keyword in lower if keyword.isascii() else keyword in text for keyword in keywords)


def _extract_json_object(raw_text: str) -> dict[str, Any]:
    text = raw_text.strip()
    try:
        data = json.loads(text)
    except json.JSONDecodeError:
        fenced_match = re.search(r"```json\s*(.*?)\s*```", text, re.DOTALL | re.IGNORECASE)
        if fenced_match:
            data = json.loads(fenced_match.group(1).strip())
        else:
            object_match = re.search(r"({.*})", text, re.DOTALL)
            if not object_match:
                raise ValueError("Failed to extract intent router JSON object.")
            data = json.loads(object_match.group(1))

    if not isinstance(data, dict):
        raise ValueError("Intent router output must be a JSON object.")
    return data


def _bounded_float(value: object, *, default: float) -> float:
    try:
        result = float(value)
    except (TypeError, ValueError):
        return default
    return min(max(result, 0.0), 1.0)
