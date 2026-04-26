from fastapi.testclient import TestClient

from app.api.routers import task as task_router
from app.integrations.fake_lark_client import FakeLarkClient
from app.integrations.hybrid_lark_client import HybridLarkClient
from app.integrations.lark_cli_client import LarkCliClient
from app.main import app
from app.services.orchestrator import AgentPilotOrchestrator
from app.services.state_service import StateService


def test_agent_pilot_task_api_flow(tmp_path, monkeypatch):
    def _build_orchestrator():
        return AgentPilotOrchestrator(StateService(tmp_path), FakeLarkClient())

    monkeypatch.setattr(task_router, "build_orchestrator", _build_orchestrator)
    client = TestClient(app)

    created = client.post(
        "/tasks",
        json={
            "message": "@Agent 生成参赛方案",
            "chat_id": "oc_demo",
            "message_id": "om_demo",
        },
    )
    assert created.status_code == 200
    created_json = created.json()
    assert created_json["status"] == "WAITING_CONFIRMATION"

    task_id = created_json["task_id"]
    confirmed = client.post(f"/tasks/{task_id}/confirm")
    assert confirmed.status_code == 200
    assert confirmed.json()["status"] == "DONE"
    assert len(confirmed.json()["artifacts"]) == 3

    revised = client.post(
        f"/tasks/{task_id}/revise",
        json={"instruction": "修改：PPT 更突出工程实现"},
    )
    assert revised.status_code == 200
    assert revised.json()["revisions"][0]["target_artifacts"] == ["slides"]

    fetched = client.get(f"/tasks/{task_id}")
    assert fetched.status_code == 200
    assert fetched.json()["task_id"] == task_id


def test_build_orchestrator_can_split_im_and_artifact_modes(monkeypatch, tmp_path):
    from types import SimpleNamespace

    monkeypatch.setattr(
        task_router,
        "get_settings",
        lambda: SimpleNamespace(
            workspace_root=str(tmp_path),
            lark_mode="fake",
            lark_im_mode="real",
            lark_artifact_mode="fake",
            lark_cli_timeout_seconds=3.0,
        ),
    )

    orchestrator = task_router.build_orchestrator()

    assert isinstance(orchestrator.lark_client, HybridLarkClient)
    assert isinstance(orchestrator.lark_client.im_client, LarkCliClient)
    assert isinstance(orchestrator.lark_client.artifact_client, FakeLarkClient)
