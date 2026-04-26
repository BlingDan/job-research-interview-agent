from app.integrations.fake_lark_client import FakeLarkClient
from app.schemas.agent_pilot import TaskCreateRequest
from app.services.orchestrator import AgentPilotOrchestrator
from app.services.state_service import StateService


def _orchestrator(tmp_path):
    return AgentPilotOrchestrator(StateService(tmp_path), FakeLarkClient())


def test_create_task_waits_for_confirmation(tmp_path):
    lark_client = FakeLarkClient()
    orchestrator = AgentPilotOrchestrator(StateService(tmp_path), lark_client)

    response = orchestrator.create_task(
        TaskCreateRequest(message="@Agent 生成参赛方案", chat_id="oc_demo", message_id="om_demo")
    )

    assert response.status == "WAITING_CONFIRMATION"
    assert response.plan is not None
    assert "确认" in response.reply
    assert lark_client.sent_messages[0]["text"] == "已理解需求，正在拆解执行计划..."
    assert lark_client.sent_messages[0]["type"] == "interactive"
    assert lark_client.sent_messages[-1]["type"] == "update"
    assert lark_client.sent_messages[-1]["text"] == response.reply


def test_create_task_falls_back_to_text_when_stream_card_fails(tmp_path):
    class NoCardFakeClient(FakeLarkClient):
        def reply_interactive_card(self, message_id: str, text: str) -> dict:
            raise RuntimeError("missing card permission")

    lark_client = NoCardFakeClient()
    orchestrator = AgentPilotOrchestrator(StateService(tmp_path), lark_client)

    response = orchestrator.create_task(
        TaskCreateRequest(message="@Agent 生成参赛方案", chat_id="oc_demo", message_id="om_demo")
    )

    assert response.status == "WAITING_CONFIRMATION"
    assert lark_client.sent_messages[-1]["reply_to_message_id"] == "om_demo"
    assert lark_client.sent_messages[-1]["text"] == response.reply


def test_confirm_generates_three_artifacts(tmp_path):
    orchestrator = _orchestrator(tmp_path)
    created = orchestrator.create_task(TaskCreateRequest(message="生成参赛方案", chat_id="oc_demo"))

    confirmed = orchestrator.confirm_task(created.task_id)

    assert confirmed.status == "DONE"
    assert {artifact.kind for artifact in confirmed.artifacts} == {"doc", "slides", "canvas"}
    assert (tmp_path / "tasks" / created.task_id / "doc.md").exists()


def test_revise_records_revision(tmp_path):
    orchestrator = _orchestrator(tmp_path)
    created = orchestrator.create_task(TaskCreateRequest(message="生成参赛方案", chat_id="oc_demo"))
    orchestrator.confirm_task(created.task_id)

    revised = orchestrator.revise_task(created.task_id, "修改：PPT 更突出工程实现")

    assert revised.status == "DONE"
    assert revised.revisions[0].target_artifacts == ["slides"]
    assert "已处理修改" in revised.reply
