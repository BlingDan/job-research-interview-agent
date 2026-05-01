from __future__ import annotations

"""
Run the Feishu IM demo bridge:

    uv run python scripts/lark_event_listener.py

For stable real-Bot verification without Doc/Slides user authorization:

    $env:LARK_IM_MODE="real"
    $env:LARK_ARTIFACT_MODE="fake"
    uv run python scripts/lark_event_listener.py

The script subscribes to lark-cli event NDJSON and routes IM messages into the
Agent-Pilot orchestrator. Tests call `handle_event_line` directly and do not
require Feishu credentials.
"""

import json
import subprocess
import sys
from pathlib import Path
from typing import TextIO

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from app.api.routers.task import build_orchestrator
from app.integrations.lark_cli_client import build_lark_cli_command
from app.services.orchestrator import AgentPilotOrchestrator
from app.services.task_message_service import TaskMessageService
from app.schemas.agent_pilot import AgentPilotResponse


def _short(value: str | None) -> str:
    if not value:
        return "-"
    if len(value) <= 12:
        return value
    return f"{value[:6]}...{value[-4:]}"


def _log(message: str) -> None:
    print(f"[Agent-Pilot] {message}", file=sys.stderr, flush=True)


_MAX_DEDUP_SET_SIZE = 1000


ROUTING_ACK_TEXT = "正在理解你的意图，稍等..."

def _extract_message_id_from_event(event: dict) -> str | None:
    raw_event = event.get("event")
    if isinstance(raw_event, dict):
        message = raw_event.get("message")
        if isinstance(message, dict):
            message_id = message.get("message_id")
            if isinstance(message_id, str) and message_id:
                return message_id
    message_id = event.get("message_id")
    if isinstance(message_id, str) and message_id:
        return message_id
    return None


def handle_event_line(
    line: str,
    orchestrator: AgentPilotOrchestrator,
    message_service: TaskMessageService,
    seen_event_ids: set[str],
) -> AgentPilotResponse | None:
    text = line.strip()
    if not text:
        return None
    event = json.loads(text)

    message_id = _extract_message_id_from_event(event)
    if message_id:
        try:
            orchestrator.lark_client.reply_message(message_id, ROUTING_ACK_TEXT)
        except Exception:
            pass

    command = message_service.parse_lark_event(event)

    if command.event_id:
        if command.event_id in seen_event_ids:
            _log(f"skipping duplicate event_id={_short(command.event_id)}")
            return None
        if len(seen_event_ids) >= _MAX_DEDUP_SET_SIZE:
            seen_event_ids.clear()
        seen_event_ids.add(command.event_id)

    _log(
        "received "
        f"type={command.type} chat={_short(command.chat_id)} "
        f"message={_short(command.message_id)}"
    )
    response = orchestrator.handle_command(command)
    if response is not None:
        _log(f"task={response.task_id} status={response.status}")
    return response


def consume_events(stream: TextIO, orchestrator: AgentPilotOrchestrator) -> None:
    message_service = TaskMessageService()
    seen_event_ids: set[str] = set()
    for line in stream:
        try:
            handle_event_line(line, orchestrator, message_service, seen_event_ids)
        except Exception as exc:
            _log(f"event handling failed: {exc}")


def build_event_subscribe_command() -> list[str]:
    return build_lark_cli_command(
        [
            "event",
            "+subscribe",
            "--as",
            "bot",
            "--force",
        ]
    )


def main() -> None:
    if "--check-imports" in sys.argv:
        print("ok")
        return

    process = subprocess.Popen(
        build_event_subscribe_command(),
        stdout=subprocess.PIPE,
        stderr=None,
        text=True,
        encoding="utf-8",
    )
    if process.stdout is None:
        raise RuntimeError("failed to open lark-cli stdout")
    consume_events(process.stdout, build_orchestrator(background_auto_confirm=True))


if __name__ == "__main__":
    main()
