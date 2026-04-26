from __future__ import annotations

import json
import os
import shutil
import subprocess
from pathlib import Path
from typing import Any

from app.schemas.agent_pilot import ArtifactRef


class LarkCliError(RuntimeError):
    pass


class LarkCliClient:
    def __init__(
        self,
        *,
        dry_run: bool = False,
        timeout_seconds: float = 30.0,
        executable: str = "lark-cli",
    ):
        self.dry_run = dry_run
        self.timeout_seconds = timeout_seconds
        self.executable = executable

    def send_message(self, chat_id: str, text: str) -> dict:
        return self._run(
            [
                "im",
                "+messages-send",
                "--as",
                "bot",
                "--chat-id",
                chat_id,
                "--msg-type",
                "text",
                "--content",
                _text_content(text),
            ]
        )

    def reply_message(self, message_id: str, text: str) -> dict:
        return self._run(
            [
                "im",
                "+messages-reply",
                "--as",
                "bot",
                "--message-id",
                message_id,
                "--msg-type",
                "text",
                "--content",
                _text_content(text),
            ]
        )

    def send_interactive_card(self, chat_id: str, text: str) -> dict:
        return self._run(
            [
                "im",
                "+messages-send",
                "--as",
                "bot",
                "--chat-id",
                chat_id,
                "--msg-type",
                "interactive",
                "--content",
                _interactive_card_content(text),
            ]
        )

    def reply_interactive_card(self, message_id: str, text: str) -> dict:
        return self._run(
            [
                "im",
                "+messages-reply",
                "--as",
                "bot",
                "--message-id",
                message_id,
                "--msg-type",
                "interactive",
                "--content",
                _interactive_card_content(text),
            ]
        )

    def update_message(self, message_id: str, text: str) -> dict:
        return self._run(
            [
                "api",
                "PATCH",
                f"/open-apis/im/v1/messages/{message_id}",
                "--data",
                json.dumps(
                    {
                        "msg_type": "interactive",
                        "content": _interactive_card_content(text),
                    },
                    ensure_ascii=False,
                ),
                "--as",
                "bot",
            ]
        )

    def create_doc(
        self, task_id: str, title: str, content: str, task_dir: Path
    ) -> ArtifactRef:
        task_dir.mkdir(parents=True, exist_ok=True)
        path = task_dir / "doc.md"
        path.write_text(content, encoding="utf-8")
        result = self._run(
            [
                "docs",
                "+create",
                "--api-version",
                "v2",
                "--as",
                "user",
                "--doc-format",
                "markdown",
                "--content",
                content,
            ]
        )
        return self._artifact_from_result(
            result,
            task_id=task_id,
            kind="doc",
            title=title,
            local_path=path,
            fallback_url=f"https://dry-run.feishu.local/doc/{task_id}",
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
        slide_payload = json.dumps([self._slide_xml(slide) for slide in slides], ensure_ascii=False)
        result = self._run(
            [
                "slides",
                "+create",
                "--as",
                "user",
                "--title",
                title,
                "--slides",
                slide_payload,
            ]
        )
        return self._artifact_from_result(
            result,
            task_id=task_id,
            kind="slides",
            title=title,
            local_path=path,
            fallback_url=f"https://dry-run.feishu.local/slides/{task_id}",
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
            url=f"https://dry-run.feishu.local/whiteboard/{task_id}",
            token=f"dry-run-whiteboard-{task_id}",
            local_path=str(path),
            status="dry_run" if self.dry_run else "fake",
            summary="已生成 Agent 编排架构画板。",
        )

    def _run(self, args: list[str]) -> dict:
        command = build_lark_cli_command(args, executable=self.executable)
        if self.dry_run and "--dry-run" not in command:
            command.append("--dry-run")

        completed = subprocess.run(
            command,
            capture_output=True,
            text=True,
            encoding="utf-8",
            timeout=self.timeout_seconds,
            check=False,
        )
        if completed.returncode != 0:
            message = completed.stderr.strip() or completed.stdout.strip()
            raise LarkCliError(message)
        return self._parse_output(completed.stdout)

    def _parse_output(self, stdout: str) -> dict:
        text = stdout.strip()
        if not text:
            return {}
        try:
            parsed = json.loads(text)
        except json.JSONDecodeError:
            return {"raw": text}
        return parsed if isinstance(parsed, dict) else {"data": parsed}

    def _artifact_from_result(
        self,
        result: dict[str, Any],
        *,
        task_id: str,
        kind: str,
        title: str,
        local_path: Path,
        fallback_url: str,
        summary: str,
    ) -> ArtifactRef:
        data = result.get("data") if isinstance(result.get("data"), dict) else result
        url = data.get("url") or data.get("document_url") or data.get("presentation_url") or fallback_url
        token = data.get("token") or data.get("document_id") or data.get("xml_presentation_id")
        return ArtifactRef(
            artifact_id=f"{task_id}-{kind}",
            kind=kind,  # type: ignore[arg-type]
            title=title,
            url=url,
            token=token,
            local_path=str(local_path),
            status="dry_run" if self.dry_run else "created",
            summary=summary,
        )

    def _slide_xml(self, slide: dict[str, str]) -> str:
        title = _escape_xml(slide.get("title", ""))
        body = _escape_xml(slide.get("body", ""))
        return (
            '<slide xmlns="http://www.larkoffice.com/sml/2.0">'
            "<style><fill><fillColor color=\"rgb(248,250,252)\"/></fill></style>"
            "<data>"
            f'<shape type="text" topLeftX="80" topLeftY="80" width="800" height="100">'
            f'<content textType="title"><p>{title}</p></content></shape>'
            f'<shape type="text" topLeftX="80" topLeftY="220" width="800" height="260">'
            f'<content textType="body"><p>{body}</p></content></shape>'
            "</data></slide>"
        )


def _escape_xml(value: str) -> str:
    return (
        value.replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace('"', "&quot;")
    )


def _text_content(text: str) -> str:
    return json.dumps({"text": text}, ensure_ascii=False)


def _interactive_card_content(text: str) -> str:
    return json.dumps(
        {
            "config": {
                "wide_screen_mode": True,
                "update_multi": True,
            },
            "elements": [
                {
                    "tag": "markdown",
                    "content": text,
                }
            ],
        },
        ensure_ascii=False,
    )


def build_lark_cli_command(
    args: list[str], *, executable: str = "lark-cli"
) -> list[str]:
    return [*_resolve_lark_cli_prefix(executable), *args]


def _resolve_lark_cli_prefix(executable: str) -> list[str]:
    found = shutil.which(executable)
    if found:
        return _command_prefix_from_path(found)

    if os.name == "nt":
        completed = subprocess.run(
            [
                "powershell.exe",
                "-NoProfile",
                "-Command",
                f"(Get-Command {executable} -ErrorAction Stop).Source",
            ],
            capture_output=True,
            text=True,
            encoding="utf-8",
            timeout=10,
            check=False,
        )
        source = completed.stdout.strip()
        if completed.returncode == 0 and source:
            return _command_prefix_from_path(source)

    return [executable]


def _command_prefix_from_path(path: str) -> list[str]:
    if path.lower().endswith(".ps1"):
        return [
            "powershell.exe",
            "-NoProfile",
            "-ExecutionPolicy",
            "Bypass",
            "-File",
            path,
        ]
    return [path]
