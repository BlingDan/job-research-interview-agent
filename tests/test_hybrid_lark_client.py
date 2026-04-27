from pathlib import Path

from app.integrations.fake_lark_client import FakeLarkClient
from app.integrations.hybrid_lark_client import HybridLarkClient


def test_hybrid_lark_client_routes_im_and_artifacts(tmp_path):
    im_client = FakeLarkClient(base_url="https://fake-im.local")
    artifact_client = FakeLarkClient(base_url="https://fake-artifact.local")
    client = HybridLarkClient(im_client=im_client, artifact_client=artifact_client)

    client.send_message("oc_demo", "hello")
    client.reply_interactive_card("om_user", "streaming")
    client.update_message("om_bot", "updated")
    artifact = client.create_doc("task-1", "方案", "# 方案", Path(tmp_path))

    assert im_client.sent_messages[0]["chat_id"] == "oc_demo"
    assert im_client.sent_messages[1]["type"] == "interactive"
    assert im_client.sent_messages[2]["updated_message_id"] == "om_bot"
    assert artifact.url == "https://fake-artifact.local/doc/task-1"
