from fastapi.testclient import TestClient

from app.core.config import get_settings
from app.main import app


def _configure_env(monkeypatch, tmp_path):
    monkeypatch.setenv("WORKSPACE_ROOT", str(tmp_path))
    monkeypatch.setenv("LARK_MODE", "fake")
    monkeypatch.setenv("LARK_IM_MODE", "fake")
    monkeypatch.setenv("LARK_ARTIFACT_MODE", "fake")
    monkeypatch.setenv("AGENT_PILOT_ROUTER_MODE", "fallback")
    monkeypatch.setenv("AGENT_PILOT_PLANNER_MODE", "fallback")
    monkeypatch.setenv("AGENT_PILOT_AUTO_CONFIRM", "false")
    get_settings.cache_clear()


def test_windows_surface_contract_flow(tmp_path, monkeypatch):
    _configure_env(monkeypatch, tmp_path)

    with TestClient(app) as client:
        created = client.post(
            "/api/im/commands",
            json={
                "message": "@Agent create an office collaboration package",
                "chat_id": "oc_windows_demo",
                "message_id": "om_windows_demo",
            },
        )
        assert created.status_code == 200
        task_id = created.json()["task_id"]

        windows_home = client.get("/api/windows/home")
        assert windows_home.status_code == 200
        assert windows_home.json()["surface"] == "windows"
        assert windows_home.json()["tasks"][0]["task_id"] == task_id

        windows_detail_before = client.get(f"/api/windows/tasks/{task_id}")
        assert windows_detail_before.status_code == 200
        assert windows_detail_before.json()["surface"] == "windows"
        assert windows_detail_before.json()["snapshot"]["task"]["task_id"] == task_id
        assert any(
            action["type"] == "confirm"
            for action in windows_detail_before.json()["snapshot"]["actions"]
        )

        confirmed = client.post(f"/api/assistant/tasks/{task_id}/actions/confirm")
        assert confirmed.status_code == 200

        windows_detail_after = client.get(f"/api/windows/tasks/{task_id}")
        assert windows_detail_after.status_code == 200
        assert windows_detail_after.json()["snapshot"]["task"]["status"] == "done"
