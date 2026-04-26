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
from typing import TextIO

from app.api.routers.task import build_orchestrator
from app.services.orchestrator import AgentPilotOrchestrator
from app.services.task_message_service import TaskMessageService
from app.schemas.agent_pilot import AgentPilotResponse


def handle_event_line(
    line: str,
    orchestrator: AgentPilotOrchestrator,
    message_service: TaskMessageService,
) -> AgentPilotResponse | None:
    text = line.strip()
    if not text:
        return None
    event = json.loads(text)
    command = message_service.parse_lark_event(event)
    return orchestrator.handle_command(command)


def consume_events(stream: TextIO, orchestrator: AgentPilotOrchestrator) -> None:
    message_service = TaskMessageService()
    for line in stream:
        handle_event_line(line, orchestrator, message_service)


def main() -> None:
    process = subprocess.Popen(
        ["lark-cli", "event", "+subscribe", "--compact"],
        stdout=subprocess.PIPE,
        stderr=None,
        text=True,
        encoding="utf-8",
    )
    if process.stdout is None:
        raise RuntimeError("failed to open lark-cli stdout")
    consume_events(process.stdout, build_orchestrator())


if __name__ == "__main__":
    main()
