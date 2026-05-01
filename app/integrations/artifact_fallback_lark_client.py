from __future__ import annotations

from pathlib import Path

from app.integrations.lark_client import LarkClient
from app.schemas.agent_pilot import ArtifactRef


class ArtifactFallbackLarkClient:
    """Try real artifact creation first, then keep the demo alive with fallback."""

    def __init__(self, *, primary: LarkClient, fallback: LarkClient):
        self.primary = primary
        self.fallback = fallback

    def send_message(self, chat_id: str, text: str) -> dict:
        return self.primary.send_message(chat_id, text)

    def reply_message(self, message_id: str, text: str) -> dict:
        return self.primary.reply_message(message_id, text)

    def send_interactive_card(self, chat_id: str, text: str) -> dict:
        return self.primary.send_interactive_card(chat_id, text)

    def reply_interactive_card(self, message_id: str, text: str) -> dict:
        return self.primary.reply_interactive_card(message_id, text)

    def update_message(self, message_id: str, text: str) -> dict:
        return self.primary.update_message(message_id, text)

    def create_doc(
        self, task_id: str, title: str, content: str, task_dir: Path
    ) -> ArtifactRef:
        try:
            return self.primary.create_doc(task_id, title, content, task_dir)
        except Exception as exc:
            artifact = self.fallback.create_doc(task_id, title, content, task_dir)
            artifact.summary = f"{artifact.summary} 真实飞书创建失败，已使用 fallback：{exc}"
            return artifact

    def create_slides(
        self, task_id: str, title: str, slides: list[dict[str, str]], task_dir: Path
    ) -> ArtifactRef:
        try:
            return self.primary.create_slides(task_id, title, slides, task_dir)
        except Exception as exc:
            artifact = self.fallback.create_slides(task_id, title, slides, task_dir)
            artifact.summary = f"{artifact.summary} 真实飞书创建失败，已使用 fallback：{exc}"
            return artifact

    def create_canvas(
        self, task_id: str, title: str, mermaid: str, task_dir: Path
    ) -> ArtifactRef:
        try:
            return self.primary.create_canvas(task_id, title, mermaid, task_dir)
        except Exception as exc:
            artifact = self.fallback.create_canvas(task_id, title, mermaid, task_dir)
            artifact.summary = f"{artifact.summary} 真实飞书创建失败，已使用 fallback：{exc}"
            return artifact

    def update_doc(
        self, task_id: str, artifact: ArtifactRef, content: str, task_dir: Path
    ) -> ArtifactRef:
        try:
            return self.primary.update_doc(task_id, artifact, content, task_dir)
        except Exception as exc:
            updated = self.fallback.update_doc(task_id, artifact, content, task_dir)
            updated.summary = f"{updated.summary} 真实飞书更新失败，已使用 fallback：{exc}"
            return updated

    def update_slides(
        self,
        task_id: str,
        artifact: ArtifactRef,
        slides: list[dict[str, str]],
        task_dir: Path,
    ) -> ArtifactRef:
        try:
            return self.primary.update_slides(task_id, artifact, slides, task_dir)
        except Exception as exc:
            updated = self.fallback.update_slides(task_id, artifact, slides, task_dir)
            updated.summary = f"{updated.summary} 真实飞书更新失败，已使用 fallback：{exc}"
            return updated

    def update_canvas(
        self, task_id: str, artifact: ArtifactRef, mermaid: str, task_dir: Path
    ) -> ArtifactRef:
        try:
            return self.primary.update_canvas(task_id, artifact, mermaid, task_dir)
        except Exception as exc:
            updated = self.fallback.update_canvas(task_id, artifact, mermaid, task_dir)
            updated.summary = f"{updated.summary} 真实飞书更新失败，已使用 fallback：{exc}"
            return updated
