from __future__ import annotations

import json
import re
from typing import Any

from app.schemas.agent_pilot import AgentPilotCommand


class TaskMessageService:
    def parse_text(
        self,
        text: str,
        *,
        chat_id: str | None = None,
        message_id: str | None = None,
        user_id: str | None = None,
        task_id: str | None = None,
    ) -> AgentPilotCommand:
        normalized = self._strip_bot_mention(text)

        if not normalized:
            command_type = "unknown"
        elif normalized == "确认":
            command_type = "confirm"
        elif normalized in {"现在做到哪了？", "现在做到哪了?", "进度", "状态"}:
            command_type = "progress"
        elif normalized.startswith(("修改：", "修改:")):
            command_type = "revise"
        else:
            command_type = "new_task"

        return AgentPilotCommand(
            type=command_type,
            text=normalized,
            chat_id=chat_id,
            message_id=message_id,
            user_id=user_id,
            task_id=task_id,
        )

    def parse_lark_event(self, event: dict[str, Any]) -> AgentPilotCommand:
        text = self._extract_text(event)
        chat_id = self._first_value(event, "chat_id", "chatId", "chat")
        message_id = self._first_value(event, "message_id", "messageId", "message")
        user_id = self._first_value(event, "user_id", "userId", "sender_id", "sender")

        raw_event = event.get("event")
        if isinstance(raw_event, dict):
            message = raw_event.get("message")
            sender = raw_event.get("sender")
            if isinstance(message, dict):
                chat_id = chat_id or message.get("chat_id")
                message_id = message_id or message.get("message_id")
            if isinstance(sender, dict):
                user_id = user_id or sender.get("sender_id", {}).get("open_id")

        return self.parse_text(
            text,
            chat_id=chat_id,
            message_id=message_id,
            user_id=user_id,
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
        for key in keys:
            value = event.get(key)
            if isinstance(value, str) and value:
                return value
        return None

    def _strip_bot_mention(self, text: str) -> str:
        stripped = (text or "").strip()
        stripped = re.sub(r"^@Agent\s*", "", stripped, flags=re.IGNORECASE)
        return stripped.strip()

