from pathlib import Path
from types import SimpleNamespace
import json

from app.integrations.lark_cli_client import LarkCliClient


def test_send_message_builds_lark_cli_command(monkeypatch):
    calls = []
    monkeypatch.setattr(
        "app.integrations.lark_cli_client._resolve_lark_cli_prefix",
        lambda executable: ["lark-cli"],
    )

    def fake_run(command, **kwargs):
        calls.append(command)
        return SimpleNamespace(returncode=0, stdout='{"data":{"message_id":"om_1"}}', stderr="")

    monkeypatch.setattr("app.integrations.lark_cli_client.subprocess.run", fake_run)
    client = LarkCliClient(dry_run=True)

    result = client.send_message("oc_demo", "hello")

    assert result["data"]["message_id"] == "om_1"
    assert calls[0][:4] == ["lark-cli", "im", "+messages-send", "--as"]
    assert "--chat-id" in calls[0]
    assert "--content" in calls[0]
    assert "--msg-type" in calls[0]
    assert "--text" not in calls[0]
    assert "--markdown" not in calls[0]
    assert "--dry-run" in calls[0]


def test_reply_message_builds_lark_cli_command(monkeypatch):
    calls = []
    monkeypatch.setattr(
        "app.integrations.lark_cli_client._resolve_lark_cli_prefix",
        lambda executable: ["lark-cli"],
    )

    def fake_run(command, **kwargs):
        calls.append(command)
        return SimpleNamespace(returncode=0, stdout="{}", stderr="")

    monkeypatch.setattr("app.integrations.lark_cli_client.subprocess.run", fake_run)
    client = LarkCliClient(dry_run=True)

    client.reply_message("om_demo", "hello")

    assert "+messages-reply" in calls[0]
    assert "--message-id" in calls[0]
    assert "--content" in calls[0]
    assert "--msg-type" in calls[0]
    assert "--text" not in calls[0]
    assert "--markdown" not in calls[0]


def test_reply_message_encodes_multiline_text_as_single_line_json(monkeypatch):
    calls = []
    monkeypatch.setattr(
        "app.integrations.lark_cli_client._resolve_lark_cli_prefix",
        lambda executable: ["lark-cli"],
    )

    def fake_run(command, **kwargs):
        calls.append(command)
        return SimpleNamespace(returncode=0, stdout="{}", stderr="")

    monkeypatch.setattr("app.integrations.lark_cli_client.subprocess.run", fake_run)
    client = LarkCliClient(dry_run=True)

    client.reply_message("om_demo", "line1\nline2")

    content = calls[0][calls[0].index("--content") + 1]
    assert "\n" not in content
    assert json.loads(content) == {"text": "line1\nline2"}


def test_update_message_uses_patch_api(monkeypatch):
    calls = []
    monkeypatch.setattr(
        "app.integrations.lark_cli_client._resolve_lark_cli_prefix",
        lambda executable: ["lark-cli"],
    )

    def fake_run(command, **kwargs):
        calls.append(command)
        return SimpleNamespace(returncode=0, stdout="{}", stderr="")

    monkeypatch.setattr("app.integrations.lark_cli_client.subprocess.run", fake_run)
    client = LarkCliClient(dry_run=True)

    client.update_message("om_bot", "line1\nline2")

    assert calls[0][1:4] == ["api", "PATCH", "/open-apis/im/v1/messages/om_bot"]
    assert "--as" in calls[0]
    assert "bot" in calls[0]
    content = calls[0][calls[0].index("--data") + 1]
    body = json.loads(content)
    assert body["msg_type"] == "interactive"
    card = json.loads(body["content"])
    assert card["elements"][0]["content"] == "line1\nline2"


def test_reply_interactive_card_builds_card_message(monkeypatch):
    calls = []
    monkeypatch.setattr(
        "app.integrations.lark_cli_client._resolve_lark_cli_prefix",
        lambda executable: ["lark-cli"],
    )

    def fake_run(command, **kwargs):
        calls.append(command)
        return SimpleNamespace(returncode=0, stdout='{"message_id":"om_card"}', stderr="")

    monkeypatch.setattr("app.integrations.lark_cli_client.subprocess.run", fake_run)
    client = LarkCliClient(dry_run=True)

    result = client.reply_interactive_card("om_user", "正在拆解")

    assert result["message_id"] == "om_card"
    assert "+messages-reply" in calls[0]
    assert "interactive" in calls[0]
    card = json.loads(calls[0][calls[0].index("--content") + 1])
    assert card["config"]["update_multi"] is True
    assert card["elements"][0]["tag"] == "markdown"


def test_create_doc_builds_v2_docs_command(tmp_path, monkeypatch):
    calls = []
    monkeypatch.setattr(
        "app.integrations.lark_cli_client._resolve_lark_cli_prefix",
        lambda executable: ["lark-cli"],
    )

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
    monkeypatch.setattr(
        "app.integrations.lark_cli_client._resolve_lark_cli_prefix",
        lambda executable: ["lark-cli"],
    )

    def fake_run(command, **kwargs):
        calls.append(command)
        return SimpleNamespace(returncode=0, stdout='{"data":{"url":"https://slides"}}', stderr="")

    monkeypatch.setattr("app.integrations.lark_cli_client.subprocess.run", fake_run)
    client = LarkCliClient(dry_run=True)

    artifact = client.create_slides("task-1", "汇报", [{"title": "封面", "body": "内容"}], Path(tmp_path))

    assert artifact.url == "https://slides"
    assert calls[0][1:3] == ["slides", "+create"]
    assert "--slides" in calls[0]


def test_build_lark_cli_command_wraps_powershell_script(monkeypatch):
    monkeypatch.setattr("app.integrations.lark_cli_client.shutil.which", lambda _: None)

    def fake_run(command, **kwargs):
        return SimpleNamespace(
            returncode=0,
            stdout="D:\\path\\nodejs\\node_global\\lark-cli.ps1\n",
            stderr="",
        )

    monkeypatch.setattr("app.integrations.lark_cli_client.subprocess.run", fake_run)

    from app.integrations.lark_cli_client import build_lark_cli_command

    command = build_lark_cli_command(["event", "+subscribe"])

    assert command[:5] == [
        "powershell.exe",
        "-NoProfile",
        "-ExecutionPolicy",
        "Bypass",
        "-File",
    ]
    assert command[-2:] == ["event", "+subscribe"]
