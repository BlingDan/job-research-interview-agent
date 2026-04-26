import json

from app.integrations.fake_lark_client import FakeLarkClient


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


def test_fake_client_records_messages():
    client = FakeLarkClient()

    sent = client.send_message("oc_demo", "hello")
    replied = client.reply_message("om_demo", "world")
    client.update_message(replied["message_id"], "updated")

    assert client.sent_messages[0]["chat_id"] == "oc_demo"
    assert client.sent_messages[1]["reply_to_message_id"] == "om_demo"
    assert sent["message_id"].startswith("om_fake_")
    assert replied["message_id"].startswith("om_fake_")
    assert client.sent_messages[2]["updated_message_id"] == replied["message_id"]
    assert client.sent_messages[2]["text"] == "updated"
