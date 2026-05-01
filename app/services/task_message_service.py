from __future__ import annotations

import json
from typing import Any

from app.agents.intent_router_agent import route_agent_pilot_message
from app.schemas.agent_pilot import AgentPilotCommand, feishu_ms_to_float_seconds, utc_now


class TaskMessageService:
    def parse_text(
        self,
        text: str,
        *,
        chat_id: str | None = None,
        message_id: str | None = None,
        user_id: str | None = None,
        task_id: str | None = None,
        event_id: str | None = None,
        event_time: float | None = None,
    ) -> AgentPilotCommand:
        route = route_agent_pilot_message(text)

        return AgentPilotCommand(
            type=route.command_type,
            text=route.text,
            chat_id=chat_id,
            message_id=message_id,
            user_id=user_id,
            task_id=task_id,
            target_artifacts=route.target_artifacts,
            route_confidence=route.confidence,
            needs_clarification=route.needs_clarification,
            route_reason=route.reason,
            route_source=route.route_source,
            event_id=event_id,
            event_time=event_time,
        )

    def parse_lark_event(self, event: dict[str, Any]) -> AgentPilotCommand:
        text = self._extract_text(event)
        chat_id = self._first_value(event, "chat_id", "chatId", "chat")
        message_id = self._first_value(event, "message_id", "messageId", "message")
        user_id = self._first_value(event, "user_id", "userId", "sender_id", "sender")

        header = event.get("header")
        event_id: str | None = None
        event_time: float | None = None
        if isinstance(header, dict):
            event_id = _first_str(header, "event_id")
            create_time_ms = _first_str(header, "create_time")
            if create_time_ms:
                event_time = feishu_ms_to_float_seconds(create_time_ms)

        raw_event = event.get("event")
        if isinstance(raw_event, dict):
            message = raw_event.get("message")
            sender = raw_event.get("sender")
            if isinstance(message, dict):
                chat_id = chat_id or message.get("chat_id")
                message_id = message_id or message.get("message_id")
                if event_time is None:
                    msg_create_time = _first_str(message, "create_time")
                    if msg_create_time:
                        event_time = feishu_ms_to_float_seconds(msg_create_time)
            if isinstance(sender, dict):
                user_id = user_id or sender.get("sender_id", {}).get("open_id")

        if event_time is None:
            event_time = feishu_ms_to_float_seconds("")

        return self.parse_text(
            text,
            chat_id=chat_id,
            message_id=message_id,
            user_id=user_id,
            event_id=event_id,
            event_time=event_time,
        )

    def _extract_text(self, event: dict[str, Any]) -> str:
        for key in ("text", "message_text", "content"):
            value = event.get(key)
            if isinstance(value, str) and value.strip():
                if key == "content":
                    return self._text_from_content(value)
                return value

        raw_event = event.get("event")
        if isinstance(raw_event, dict):
            message = raw_event.get("message")
            if isinstance(message, dict):
                content = message.get("content")
                if isinstance(content, str):
                    return self._text_from_content(content)
        return ""

    def _text_from_content(self, content: str) -> str:
        try:
            data = json.loads(content)
        except json.JSONDecodeError:
            return content
        if isinstance(data, dict):
            value = data.get("text") or data.get("content") or ""
            return str(value)
        return content

    def _first_value(self, event: dict[str, Any], *keys: str) -> str | None:
        return _first_str_multi(event, keys)


def _first_str_multi(mapping: dict[str, Any], keys: tuple[str, ...]) -> str | None:
    for key in keys:
        value = mapping.get(key)
        if isinstance(value, str) and value:
            return value
    return None


def _first_str(mapping: dict[str, Any], key: str) -> str | None:
    value = mapping.get(key)
    return value if isinstance(value, str) and value else None
