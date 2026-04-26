from __future__ import annotations

import json
from pathlib import Path

from app.schemas.agent_pilot import ArtifactRef


class FakeLarkClient:
    def __init__(self, base_url: str = "https://fake.feishu.local"):
        self.base_url = base_url.rstrip("/")
        self.sent_messages: list[dict] = []
        self._message_counter = 0

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
            summary="已生成参赛方案文档。",
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
            summary="已生成 5 页答辩汇报材料。",
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
        )
