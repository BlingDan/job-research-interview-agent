from __future__ import annotations

import json
from pathlib import Path

from app.schemas.agent_pilot import ArtifactRef


class FakeLarkClient:
    def __init__(self, base_url: str = "https://fake.feishu.local"):
        self.base_url = base_url.rstrip("/")
        self.sent_messages: list[dict] = []
        self._message_counter = 0
        self._chat_histories: dict[str, list[dict]] = {}

    def seed_chat_history(self, chat_id: str, messages: list[dict]) -> None:
        """Pre-populate chat history for testing/demo. Each message: {sender_name, content, timestamp}"""
        self._chat_histories[chat_id] = messages

    def fetch_recent_messages(self, chat_id: str, limit: int = 50) -> list[dict]:
        history = self._chat_histories.get(chat_id, [])
        return history[-limit:] if len(history) > limit else history

    def send_message(self, chat_id: str, text: str) -> dict:
        payload = {"mode": "fake", "chat_id": chat_id, "text": text, "message_id": self._next_message_id()}
        self.sent_messages.append(payload)
        return payload

    def reply_message(self, message_id: str, text: str) -> dict:
        payload = {
            "mode": "fake",
            "message_id": self._next_message_id(),
            "reply_to_message_id": message_id,
            "text": text,
        }
        self.sent_messages.append(payload)
        return payload

    def send_interactive_card(self, chat_id: str, text: str) -> dict:
        payload = {
            "mode": "fake",
            "type": "interactive",
            "chat_id": chat_id,
            "text": text,
            "message_id": self._next_message_id(),
        }
        self.sent_messages.append(payload)
        return payload

    def reply_interactive_card(self, message_id: str, text: str) -> dict:
        payload = {
            "mode": "fake",
            "type": "interactive",
            "message_id": self._next_message_id(),
            "reply_to_message_id": message_id,
            "text": text,
        }
        self.sent_messages.append(payload)
        return payload

    def update_message(self, message_id: str, text: str) -> dict:
        payload = {
            "mode": "fake",
            "type": "update",
            "updated_message_id": message_id,
            "text": text,
        }
        self.sent_messages.append(payload)
        return payload

    def _next_message_id(self) -> str:
        self._message_counter += 1
        return f"om_fake_{self._message_counter}"

    def create_doc(
        self, task_id: str, title: str, content: str, task_dir: Path
    ) -> ArtifactRef:
        task_dir.mkdir(parents=True, exist_ok=True)
        path = task_dir / "doc.md"
        path.write_text(content, encoding="utf-8")
        return ArtifactRef(
            artifact_id=f"{task_id}-doc",
            kind="doc",
            title=title,
            url=f"{self.base_url}/doc/{task_id}",
            token=f"fake-doc-{task_id}",
            local_path=str(path),
            status="fake",
            summary="已生成项目方案文档。",
            metadata={"source_format": "markdown"},
        )

    def create_slides(
        self, task_id: str, title: str, slides: list[dict[str, str]], task_dir: Path
    ) -> ArtifactRef:
        task_dir.mkdir(parents=True, exist_ok=True)
        path = task_dir / "slides.json"
        path.write_text(
            json.dumps(slides, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        return ArtifactRef(
            artifact_id=f"{task_id}-slides",
            kind="slides",
            title=title,
            url=f"{self.base_url}/slides/{task_id}",
            token=f"fake-slides-{task_id}",
            local_path=str(path),
            status="fake",
            summary="已生成 5 页汇报演示文稿。",
            metadata={
                "source_format": "json",
                "slide_ids": [f"fake-slide-{index}" for index, _ in enumerate(slides, start=1)],
            },
        )

    def create_canvas(
        self, task_id: str, title: str, mermaid: str, task_dir: Path
    ) -> ArtifactRef:
        task_dir.mkdir(parents=True, exist_ok=True)
        path = task_dir / "canvas.mmd"
        path.write_text(mermaid, encoding="utf-8")
        return ArtifactRef(
            artifact_id=f"{task_id}-canvas",
            kind="canvas",
            title=title,
            url=f"{self.base_url}/whiteboard/{task_id}",
            token=f"fake-whiteboard-{task_id}",
            local_path=str(path),
            status="fake",
            summary="已生成 Agent 编排架构画板。",
            metadata={"source_format": "mermaid", "whiteboard_token": f"fake-whiteboard-{task_id}"},
        )

    def update_doc(
        self, task_id: str, artifact: ArtifactRef, content: str, task_dir: Path
    ) -> ArtifactRef:
        task_dir.mkdir(parents=True, exist_ok=True)
        path = Path(artifact.local_path) if artifact.local_path else task_dir / "doc.md"
        path.write_text(content, encoding="utf-8")
        return artifact.model_copy(
            update={
                "local_path": str(path),
                "status": "updated",
                "summary": "已原地更新项目方案文档。",
                "metadata": {**artifact.metadata, "source_format": "markdown"},
            }
        )

    def update_slides(
        self,
        task_id: str,
        artifact: ArtifactRef,
        slides: list[dict[str, str]],
        task_dir: Path,
    ) -> ArtifactRef:
        task_dir.mkdir(parents=True, exist_ok=True)
        path = Path(artifact.local_path) if artifact.local_path else task_dir / "slides.json"
        path.write_text(
            json.dumps(slides, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        metadata = {
            **artifact.metadata,
            "source_format": "json",
            "slide_ids": artifact.metadata.get("slide_ids")
            or [f"fake-slide-{index}" for index, _ in enumerate(slides, start=1)],
        }
        return artifact.model_copy(
            update={
                "local_path": str(path),
                "status": "updated",
                "summary": "已原地更新 5 页汇报演示文稿。",
                "metadata": metadata,
            }
        )

    def update_canvas(
        self, task_id: str, artifact: ArtifactRef, mermaid: str, task_dir: Path
    ) -> ArtifactRef:
        task_dir.mkdir(parents=True, exist_ok=True)
        path = Path(artifact.local_path) if artifact.local_path else task_dir / "canvas.mmd"
        path.write_text(mermaid, encoding="utf-8")
        metadata = {
            **artifact.metadata,
            "source_format": "mermaid",
            "whiteboard_token": artifact.metadata.get("whiteboard_token") or artifact.token,
        }
        return artifact.model_copy(
            update={
                "local_path": str(path),
                "status": "updated",
                "summary": "已原地更新 Agent 编排架构画板。",
                "metadata": metadata,
            }
        )
