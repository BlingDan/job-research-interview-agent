from app.integrations.fake_lark_client import FakeLarkClient
from app.schemas.agent_pilot import TaskCreateRequest
from app.services.orchestrator import AgentPilotOrchestrator
from app.services.state_service import StateService
from app.services.task_message_service import TaskMessageService
from scripts.lark_event_listener import handle_event_line


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

