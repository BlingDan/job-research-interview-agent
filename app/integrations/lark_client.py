from __future__ import annotations

from pathlib import Path
from typing import Protocol

from app.schemas.agent_pilot import ArtifactRef


class LarkClient(Protocol):
    def send_message(self, chat_id: str, text: str) -> dict:
        ...

    def reply_message(self, message_id: str, text: str) -> dict:
        ...

    def update_message(self, message_id: str, text: str) -> dict:
        ...

    def create_doc(
        self, task_id: str, title: str, content: str, task_dir: Path
    ) -> ArtifactRef:
        ...

    def create_slides(
        self, task_id: str, title: str, slides: list[dict[str, str]], task_dir: Path
    ) -> ArtifactRef:
        ...

    def create_canvas(
        self, task_id: str, title: str, mermaid: str, task_dir: Path
    ) -> ArtifactRef:
        ...
