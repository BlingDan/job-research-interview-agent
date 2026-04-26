from __future__ import annotations

from pathlib import Path

from app.integrations.lark_client import LarkClient
from app.schemas.agent_pilot import ArtifactRef


class HybridLarkClient:
    def __init__(self, *, im_client: LarkClient, artifact_client: LarkClient):
        self.im_client = im_client
        self.artifact_client = artifact_client

    def send_message(self, chat_id: str, text: str) -> dict:
        return self.im_client.send_message(chat_id, text)

    def reply_message(self, message_id: str, text: str) -> dict:
        return self.im_client.reply_message(message_id, text)

    def send_interactive_card(self, chat_id: str, text: str) -> dict:
        return self.im_client.send_interactive_card(chat_id, text)

    def reply_interactive_card(self, message_id: str, text: str) -> dict:
        return self.im_client.reply_interactive_card(message_id, text)

    def update_message(self, message_id: str, text: str) -> dict:
        return self.im_client.update_message(message_id, text)

    def create_doc(
        self, task_id: str, title: str, content: str, task_dir: Path
    ) -> ArtifactRef:
        return self.artifact_client.create_doc(task_id, title, content, task_dir)

    def create_slides(
        self, task_id: str, title: str, slides: list[dict[str, str]], task_dir: Path
    ) -> ArtifactRef:
        return self.artifact_client.create_slides(task_id, title, slides, task_dir)

    def create_canvas(
        self, task_id: str, title: str, mermaid: str, task_dir: Path
    ) -> ArtifactRef:
        return self.artifact_client.create_canvas(task_id, title, mermaid, task_dir)
