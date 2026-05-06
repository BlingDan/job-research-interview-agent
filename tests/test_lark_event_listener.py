from app.integrations.fake_lark_client import FakeLarkClient
from app.assistant.orchestrator import AgentPilotOrchestrator
from app.schemas.agent_pilot import TaskCreateRequest
from app.shared.state_service import StateService
from app.services.task_message_service import TaskMessageService
from scripts.lark_event_listener import (
    handle_event_line,
    build_event_subscribe_command,
)
import subprocess
import sys


def _empty_seen() -> set[str]:
    return set()


def test_handle_event_line_routes_event(tmp_path):
    orchestrator = AgentPilotOrchestrator(StateService(tmp_path), FakeLarkClient())
    line = (
        '{"text":"@Agent 生成参赛方案","chat_id":"oc_demo",'
        '"message_id":"om_demo","user_id":"ou_demo"}'
    )

    response = handle_event_line(line, orchestrator, TaskMessageService(), _empty_seen())

    assert response is not None
    assert response.status == "WAITING_CONFIRMATION"


def test_handle_event_line_routes_followup_confirm(tmp_path):
    orchestrator = AgentPilotOrchestrator(StateService(tmp_path), FakeLarkClient())
    created = orchestrator.create_task(TaskCreateRequest(message="生成参赛方案", chat_id="oc_demo"))
    line = '{"text":"确认","chat_id":"oc_demo","message_id":"om_demo"}'

    response = handle_event_line(line, orchestrator, TaskMessageService(), _empty_seen())

    assert response is not None
    assert response.task_id == created.task_id
    assert response.status == "DONE"


def test_handle_event_line_replies_to_ping_without_creating_task(tmp_path):
    lark_client = FakeLarkClient()
    orchestrator = AgentPilotOrchestrator(StateService(tmp_path), lark_client)
    line = '{"text":"ping","chat_id":"oc_demo","message_id":"om_demo"}'

    response = handle_event_line(line, orchestrator, TaskMessageService(), _empty_seen())

    assert response is None
    assert lark_client.sent_messages[-1]["reply_to_message_id"] == "om_demo"
    assert "在线" in lark_client.sent_messages[-1]["text"]
    assert not (tmp_path / "indexes" / "chat_tasks.json").exists()


def test_listener_script_can_be_executed_by_path():
    completed = subprocess.run(
        [sys.executable, "scripts/lark_event_listener.py", "--check-imports"],
        capture_output=True,
        text=True,
        encoding="utf-8",
        check=False,
    )

    assert completed.returncode == 0
    assert completed.stdout.strip() == "ok"


def test_event_subscribe_command_uses_bot_identity_and_no_longer_compact(monkeypatch):
    monkeypatch.setattr(
        "scripts.lark_event_listener.build_lark_cli_command",
        lambda args: ["lark-cli", *args],
    )

    command = build_event_subscribe_command()

    assert "--compact" not in command
    assert command == [
        "lark-cli",
        "event",
        "+subscribe",
        "--as",
        "bot",
        "--force",
    ]


def test_handle_event_line_deduplicates_by_event_id(tmp_path):
    lark_client = FakeLarkClient()
    orchestrator = AgentPilotOrchestrator(StateService(tmp_path), lark_client)
    seen: set[str] = set()

    line = (
        '{"event":{"message":{"message_id":"om_demo","chat_id":"oc_demo","content":"{\\"text\\":\\"确认\\"}"},'
        '"sender":{"sender_id":{"open_id":"ou_demo"}}},'
        '"header":{"event_id":"evt-001","create_time":"1700000000000"}}'
    )
    orchestrator.create_task(TaskCreateRequest(message="在先任务", chat_id="oc_demo"))

    response1 = handle_event_line(line, orchestrator, TaskMessageService(), seen)
    assert seen == {"evt-001"}

    response2 = handle_event_line(line, orchestrator, TaskMessageService(), seen)
    assert response2 is None
