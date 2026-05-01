import json

from app.integrations.fake_lark_client import FakeLarkClient
from app.schemas.agent_pilot import ArtifactRef


def test_fake_client_writes_artifacts(tmp_path):
    client = FakeLarkClient()

    doc = client.create_doc("task-1", "方案", "# 方案", tmp_path)
    slides = client.create_slides("task-1", "汇报", [{"title": "封面"}], tmp_path)
    canvas = client.create_canvas("task-1", "画板", "flowchart LR", tmp_path)

    assert doc.url == "https://fake.feishu.local/doc/task-1"
    assert (tmp_path / "doc.md").read_text(encoding="utf-8") == "# 方案"
    assert json.loads((tmp_path / "slides.json").read_text(encoding="utf-8"))[0]["title"] == "封面"
    assert (tmp_path / "canvas.mmd").read_text(encoding="utf-8") == "flowchart LR"
    assert canvas.status == "fake"


def test_fake_client_updates_artifacts_in_place(tmp_path):
    client = FakeLarkClient()
    doc = client.create_doc("task-1", "方案", "# 方案", tmp_path)
    slides = client.create_slides("task-1", "汇报", [{"title": "封面", "body": "旧"}], tmp_path)
    canvas = client.create_canvas("task-1", "画板", "flowchart LR\nA-->B", tmp_path)

    updated_doc = client.update_doc("task-1", doc, "2026-04-28 16:57\n# 方案", tmp_path)
    updated_slides = client.update_slides(
        "task-1", slides, [{"title": "封面", "body": "新工程实现"}], tmp_path
    )
    updated_canvas = client.update_canvas("task-1", canvas, "flowchart LR\nA-->B\nB-->C", tmp_path)

    assert updated_doc.url == doc.url
    assert updated_doc.token == doc.token
    assert updated_doc.status == "updated"
    assert updated_slides.url == slides.url
    assert updated_slides.token == slides.token
    assert updated_slides.status == "updated"
    assert updated_canvas.url == canvas.url
    assert updated_canvas.token == canvas.token
    assert updated_canvas.status == "updated"
    assert (tmp_path / "doc.md").read_text(encoding="utf-8").startswith("2026-04-28 16:57")
    assert json.loads((tmp_path / "slides.json").read_text(encoding="utf-8"))[0]["body"] == "新工程实现"
    assert (tmp_path / "canvas.mmd").read_text(encoding="utf-8").endswith("B-->C")


def test_fake_client_can_update_existing_ref_without_local_path(tmp_path):
    client = FakeLarkClient()
    artifact = ArtifactRef(
        artifact_id="task-1-doc",
        kind="doc",
        title="方案",
        url="https://fake.feishu.local/doc/task-1",
        token="fake-doc-task-1",
        status="fake",
    )

    updated = client.update_doc("task-1", artifact, "# 新方案", tmp_path)

    assert updated.local_path == str(tmp_path / "doc.md")
    assert updated.url == artifact.url


def test_fake_client_records_messages():
    client = FakeLarkClient()

    sent = client.send_message("oc_demo", "hello")
    replied = client.reply_message("om_demo", "world")
    card = client.reply_interactive_card("om_demo", "streaming")
    client.update_message(replied["message_id"], "updated")

    assert client.sent_messages[0]["chat_id"] == "oc_demo"
    assert client.sent_messages[1]["reply_to_message_id"] == "om_demo"
    assert sent["message_id"].startswith("om_fake_")
    assert replied["message_id"].startswith("om_fake_")
    assert card["message_id"].startswith("om_fake_")
    assert client.sent_messages[2]["type"] == "interactive"
    assert client.sent_messages[3]["updated_message_id"] == replied["message_id"]
    assert client.sent_messages[3]["text"] == "updated"
