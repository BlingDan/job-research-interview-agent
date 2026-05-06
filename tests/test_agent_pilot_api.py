import json

from fastapi.testclient import TestClient

from app.assistant import runtime as assistant_runtime
from app.core.config import get_settings
from app.integrations.artifact_fallback_lark_client import ArtifactFallbackLarkClient
from app.integrations.fake_lark_client import FakeLarkClient
from app.integrations.hybrid_lark_client import HybridLarkClient
from app.integrations.lark_cli_client import LarkCliClient
from app.main import app
from app.integrations.artifacts import FeishuMcpToolAdapter


def _configure_env(monkeypatch, tmp_path):
    monkeypatch.setenv("WORKSPACE_ROOT", str(tmp_path))
    monkeypatch.setenv("LARK_MODE", "fake")
    monkeypatch.setenv("LARK_IM_MODE", "fake")
    monkeypatch.setenv("LARK_ARTIFACT_MODE", "fake")
    monkeypatch.setenv("AGENT_PILOT_ROUTER_MODE", "fallback")
    monkeypatch.setenv("AGENT_PILOT_PLANNER_MODE", "fallback")
    monkeypatch.setenv("AGENT_PILOT_AUTO_CONFIRM", "false")
    get_settings.cache_clear()


def _patch_revision_llm(monkeypatch):
    from app.agents import artifact_revision_agent

    class FakeRevisionLLM:
        def __init__(self, **kwargs):
            pass

        def invoke(self, messages):
            return json.dumps(
                {
                    "content": "# 标题\n更新后的内容",
                    "change_summary": "已更新文档内容",
                }
            )

    monkeypatch.setattr(artifact_revision_agent, "JobResearchLLM", FakeRevisionLLM)


def test_im_command_and_assistant_action_flow(tmp_path, monkeypatch):
    _configure_env(monkeypatch, tmp_path)
    _patch_revision_llm(monkeypatch)

    with TestClient(app) as client:
        created = client.post(
            "/api/im/commands",
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

        fetched = client.get(f"/api/assistant/tasks/{task_id}")
        assert fetched.status_code == 200
        assert fetched.json()["task_id"] == task_id

        confirmed = client.post(f"/api/assistant/tasks/{task_id}/actions/confirm")
        assert confirmed.status_code == 200
        assert confirmed.json()["status"] == "DONE"
        assert len(confirmed.json()["artifacts"]) == 3

        revised = client.post(
            f"/api/assistant/tasks/{task_id}/actions/revise",
            json={"instruction": "修改：PPT 更突出工程实现"},
        )
        assert revised.status_code == 200
        assert revised.json()["revisions"][0]["target_artifacts"] == ["slides"]


def test_im_event_and_surface_snapshot_endpoints(tmp_path, monkeypatch):
    _configure_env(monkeypatch, tmp_path)
    _patch_revision_llm(monkeypatch)

    with TestClient(app) as client:
        created = client.post(
            "/api/im/commands",
            json={
                "message": "@Agent 生成参赛方案",
                "chat_id": "oc_demo",
                "message_id": "om_demo",
            },
        ).json()
        task_id = created["task_id"]

        event_response = client.post(
            "/api/im/events",
            json={
                "event": {
                    "message": {
                        "message_id": "om_followup",
                        "chat_id": "oc_demo",
                        "content": "{\"text\":\"确认\"}",
                    },
                    "sender": {"sender_id": {"open_id": "ou_demo"}},
                },
                "header": {"event_id": "evt-001", "create_time": "1700000000000"},
            },
        )
        assert event_response.status_code == 200
        assert event_response.json()["task_id"] == task_id
        assert event_response.json()["status"] == "DONE"

        cockpit_list = client.get("/api/cockpit/tasks")
        assert cockpit_list.status_code == 200
        assert cockpit_list.json()["tasks"][0]["task_id"] == task_id

        cockpit_detail = client.get(f"/api/cockpit/tasks/{task_id}")
        assert cockpit_detail.status_code == 200
        assert cockpit_detail.json()["task_id"] == task_id

        windows_home = client.get("/api/windows/home")
        assert windows_home.status_code == 200
        assert windows_home.json()["surface"] == "windows"
        assert windows_home.json()["tasks"][0]["task_id"] == task_id

        mobile_home = client.get("/api/mobile/home")
        assert mobile_home.status_code == 200
        assert mobile_home.json()["surface"] == "mobile"
        assert mobile_home.json()["tasks"][0]["task_id"] == task_id

        windows_detail = client.get(f"/api/windows/tasks/{task_id}")
        assert windows_detail.status_code == 200
        assert windows_detail.json()["surface"] == "windows"
        assert windows_detail.json()["snapshot"]["task"]["task_id"] == task_id

        mobile_detail = client.get(f"/api/mobile/tasks/{task_id}")
        assert mobile_detail.status_code == 200
        assert mobile_detail.json()["surface"] == "mobile"
        assert mobile_detail.json()["snapshot"]["task"]["task_id"] == task_id


def test_cockpit_task_websocket_streams_initial_state(tmp_path, monkeypatch):
    _configure_env(monkeypatch, tmp_path)
    _patch_revision_llm(monkeypatch)

    with TestClient(app) as client:
        created = client.post(
            "/api/im/commands",
            json={"message": "@Agent 生成参赛方案", "chat_id": "oc_demo"},
        ).json()

        with client.websocket_connect(f"/api/cockpit/ws/tasks/{created['task_id']}") as websocket:
            payload = websocket.receive_json()

        assert payload["type"] == "task_state"
        assert payload["data"]["task_id"] == created["task_id"]


def test_build_orchestrator_can_split_im_and_artifact_modes(monkeypatch, tmp_path):
    from types import SimpleNamespace

    monkeypatch.setattr(
        assistant_runtime,
        "get_settings",
        lambda: SimpleNamespace(
            workspace_root=str(tmp_path),
            lark_mode="fake",
            lark_im_mode="real",
            lark_artifact_mode="fake",
            lark_cli_timeout_seconds=3.0,
            lark_stream_delay_seconds=0.0,
            agent_pilot_auto_confirm=False,
            agent_pilot_background_auto_confirm=False,
            feishu_tool_mode="hybrid",
            feishu_mcp_mode="off",
            feishu_mcp_app_id="",
            feishu_mcp_app_secret="",
            feishu_mcp_domain="https://open.feishu.cn",
            feishu_mcp_tools="docx.builtin.import",
            feishu_mcp_timeout_seconds=9.0,
            feishu_mcp_token_mode="tenant_access_token",
            feishu_mcp_use_uat=False,
            feishu_tool_adapter_timeout_seconds=10.0,
        ),
    )

    orchestrator = assistant_runtime.build_orchestrator()

    assert isinstance(orchestrator.lark_client, HybridLarkClient)
    assert isinstance(orchestrator.lark_client.im_client, LarkCliClient)
    assert isinstance(orchestrator.lark_client.artifact_client, FakeLarkClient)


def test_build_orchestrator_wraps_real_artifacts_with_fallback(monkeypatch, tmp_path):
    from types import SimpleNamespace

    monkeypatch.setattr(
        assistant_runtime,
        "get_settings",
        lambda: SimpleNamespace(
            workspace_root=str(tmp_path),
            lark_mode="fake",
            lark_im_mode="real",
            lark_artifact_mode="real",
            lark_cli_timeout_seconds=3.0,
            lark_stream_delay_seconds=0.0,
            agent_pilot_auto_confirm=False,
            agent_pilot_background_auto_confirm=False,
            feishu_tool_mode="hybrid",
            feishu_mcp_mode="real",
            feishu_mcp_app_id="cli_demo",
            feishu_mcp_app_secret="secret-value",
            feishu_mcp_domain="https://open.feishu.cn",
            feishu_mcp_tools="docx.builtin.import",
            feishu_mcp_timeout_seconds=9.0,
            feishu_mcp_token_mode="tenant_access_token",
            feishu_mcp_use_uat=False,
            feishu_tool_adapter_timeout_seconds=10.0,
        ),
    )

    orchestrator = assistant_runtime.build_orchestrator()

    assert isinstance(orchestrator.lark_client, HybridLarkClient)
    assert isinstance(orchestrator.lark_client.artifact_client, ArtifactFallbackLarkClient)
    assert isinstance(orchestrator.tool_layer.adapters["mcp"], FeishuMcpToolAdapter)
    assert orchestrator.tool_layer.adapters["mcp"].mode == "real"
    assert orchestrator.tool_layer.adapters["mcp"].use_uat is False
    assert orchestrator.tool_layer.adapters["mcp"].client.token_mode == "tenant_access_token"
