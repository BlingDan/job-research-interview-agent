from pathlib import Path
from types import SimpleNamespace

from app.integrations.lark_cli_client import LarkCliClient


def test_send_message_builds_lark_cli_command(monkeypatch):
    calls = []

    def fake_run(command, **kwargs):
        calls.append(command)
        return SimpleNamespace(returncode=0, stdout='{"data":{"message_id":"om_1"}}', stderr="")

    monkeypatch.setattr("app.integrations.lark_cli_client.subprocess.run", fake_run)
    client = LarkCliClient(dry_run=True)

    result = client.send_message("oc_demo", "hello")

    assert result["data"]["message_id"] == "om_1"
    assert calls[0][:4] == ["lark-cli", "im", "+messages-send", "--as"]
    assert "--chat-id" in calls[0]
    assert "--dry-run" in calls[0]


def test_reply_message_builds_lark_cli_command(monkeypatch):
    calls = []

    def fake_run(command, **kwargs):
        calls.append(command)
        return SimpleNamespace(returncode=0, stdout="{}", stderr="")

    monkeypatch.setattr("app.integrations.lark_cli_client.subprocess.run", fake_run)
    client = LarkCliClient(dry_run=True)

    client.reply_message("om_demo", "hello")

    assert "+messages-reply" in calls[0]
    assert "--message-id" in calls[0]


def test_create_doc_builds_v2_docs_command(tmp_path, monkeypatch):
    calls = []

    def fake_run(command, **kwargs):
        calls.append(command)
        return SimpleNamespace(returncode=0, stdout='{"data":{"url":"https://doc"}}', stderr="")

    monkeypatch.setattr("app.integrations.lark_cli_client.subprocess.run", fake_run)
    client = LarkCliClient(dry_run=True)

    artifact = client.create_doc("task-1", "方案", "# 方案", Path(tmp_path))

    assert artifact.url == "https://doc"
    assert calls[0][1:5] == ["docs", "+create", "--api-version", "v2"]
    assert (tmp_path / "doc.md").exists()


def test_create_slides_builds_slides_command(tmp_path, monkeypatch):
    calls = []

    def fake_run(command, **kwargs):
        calls.append(command)
        return SimpleNamespace(returncode=0, stdout='{"data":{"url":"https://slides"}}', stderr="")

    monkeypatch.setattr("app.integrations.lark_cli_client.subprocess.run", fake_run)
    client = LarkCliClient(dry_run=True)

    artifact = client.create_slides("task-1", "汇报", [{"title": "封面", "body": "内容"}], Path(tmp_path))

    assert artifact.url == "https://slides"
    assert calls[0][1:3] == ["slides", "+create"]
    assert "--slides" in calls[0]

