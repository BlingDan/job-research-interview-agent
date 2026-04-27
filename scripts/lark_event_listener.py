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


def build_event_subscribe_command() -> list[str]:
    return build_lark_cli_command(
        [
            "event",
            "+subscribe",
            "--as",
            "bot",
            "--compact",
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
    consume_events(process.stdout, build_orchestrator())


if __name__ == "__main__":
    main()
