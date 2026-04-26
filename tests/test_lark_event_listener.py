from app.integrations.fake_lark_client import FakeLarkClient
from app.schemas.agent_pilot import TaskCreateRequest
from app.services.orchestrator import AgentPilotOrchestrator
from app.services.state_service import StateService
from app.services.task_message_service import TaskMessageService
from scripts.lark_event_listener import handle_event_line
import subprocess
import sys


def test_handle_event_line_routes_event(tmp_path):
    orchestrator = AgentPilotOrchestrator(StateService(tmp_path), FakeLarkClient())
    line = (
        '{"text":"@Agent 生成参赛方案","chat_id":"oc_demo",'
        '"message_id":"om_demo","user_id":"ou_demo"}'
    )

    response = handle_event_line(line, orchestrator, TaskMessageService())

    assert response is not None
    assert response.status == "WAITING_CONFIRMATION"


def test_handle_event_line_routes_followup_confirm(tmp_path):
    orchestrator = AgentPilotOrchestrator(StateService(tmp_path), FakeLarkClient())
    created = orchestrator.create_task(TaskCreateRequest(message="生成参赛方案", chat_id="oc_demo"))
    line = '{"text":"确认","chat_id":"oc_demo","message_id":"om_demo"}'

    response = handle_event_line(line, orchestrator, TaskMessageService())

    assert response is not None
    assert response.task_id == created.task_id
    assert response.status == "DONE"


def test_handle_event_line_replies_to_ping_without_creating_task(tmp_path):
    lark_client = FakeLarkClient()
    orchestrator = AgentPilotOrchestrator(StateService(tmp_path), lark_client)
    line = '{"text":"ping","chat_id":"oc_demo","message_id":"om_demo"}'

    response = handle_event_line(line, orchestrator, TaskMessageService())

    assert response is None
    assert lark_client.sent_messages[-1]["message_id"] == "om_demo"
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
