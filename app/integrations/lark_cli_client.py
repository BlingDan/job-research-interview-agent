from __future__ import annotations

import json
import os
import shutil
import subprocess
import uuid
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
                "--title",
                title,
                "--doc-format",
                "markdown",
                "--content",
                f"@{path.as_posix()}",
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
        artifact = self._artifact_from_result(
            result,
            task_id=task_id,
            kind="slides",
            title=title,
            local_path=path,
            fallback_url=f"https://dry-run.feishu.local/slides/{task_id}",
            summary="已生成 5 页答辩汇报材料。",
            metadata={
                "source_format": "json",
                "slide_ids": _extract_slide_ids(result),
            },
        )
        if not self.dry_run and artifact.token and _is_fallback_url(artifact.url):
            metadata_url = self._drive_meta_url(artifact.token, "slides")
            if metadata_url:
                artifact.url = metadata_url
        return artifact

    def create_canvas(
        self, task_id: str, title: str, mermaid: str, task_dir: Path
    ) -> ArtifactRef:
        task_dir.mkdir(parents=True, exist_ok=True)
        path = task_dir / "canvas.mmd"
        path.write_text(mermaid, encoding="utf-8")
        try:
            result = self._run(
                [
                    "docs",
                    "+create",
                    "--api-version",
                    "v2",
                    "--as",
                    "user",
                    "--title",
                    title,
                    "--doc-format",
                    "markdown",
                    "--content",
                    f"@{_write_whiteboard_doc_seed(task_dir, title).as_posix()}",
                ]
            )
        except LarkCliError as exc:
            if not self.dry_run:
                raise
            return ArtifactRef(
                artifact_id=f"{task_id}-canvas",
                kind="canvas",
                title=title,
                url=f"https://dry-run.feishu.local/whiteboard/{task_id}",
                token=f"dry-run-whiteboard-{task_id}",
                local_path=str(path),
                status="dry_run",
                summary=f"画板 dry-run 未执行：{exc}",
                metadata={
                    "source_format": "mermaid",
                    "whiteboard_token": f"dry-run-whiteboard-{task_id}",
                },
            )
        board_token = _extract_whiteboard_token(result)
        doc_url = _first_result_value(result, "url", "document_url")
        doc_token = _first_result_value(result, "document_id", "token")
        if board_token:
            self._run(
                [
                    "whiteboard",
                    "+update",
                    "--as",
                    "user",
                    "--whiteboard-token",
                    board_token,
                    "--source",
                    f"@{path.as_posix()}",
                    "--input_format",
                    "mermaid",
                    "--idempotent-token",
                    f"agentpilot-{uuid.uuid4().hex[:16]}",
                    "--overwrite",
                    "--yes",
                ]
            )
        return ArtifactRef(
            artifact_id=f"{task_id}-canvas",
            kind="canvas",
            title=title,
            url=doc_url or f"https://dry-run.feishu.local/whiteboard/{task_id}",
            token=board_token or doc_token or f"dry-run-whiteboard-{task_id}",
            local_path=str(path),
            status="dry_run" if self.dry_run else "created",
            summary="已生成 Agent 编排架构画板。",
            metadata={
                "source_format": "mermaid",
                "whiteboard_token": board_token or doc_token or f"dry-run-whiteboard-{task_id}",
                "doc_token": doc_token,
            },
        )

    def update_doc(
        self, task_id: str, artifact: ArtifactRef, content: str, task_dir: Path
    ) -> ArtifactRef:
        task_dir.mkdir(parents=True, exist_ok=True)
        path = Path(artifact.local_path) if artifact.local_path else task_dir / "doc.md"
        path.write_text(content, encoding="utf-8")
        doc_ref = artifact.token or artifact.url
        if not doc_ref:
            raise LarkCliError("missing doc token/url for in-place update")
        self._run(
            [
                "docs",
                "+update",
                "--api-version",
                "v2",
                "--as",
                "user",
                "--doc",
                doc_ref,
                "--mode",
                "overwrite",
                "--markdown",
                f"@{path.as_posix()}",
            ]
        )
        return artifact.model_copy(
            update={
                "local_path": str(path),
                "status": "updated",
                "summary": "已原地更新参赛方案文档。",
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
        presentation = artifact.token or artifact.url
        if not presentation:
            raise LarkCliError("missing presentation token/url for in-place update")
        slide_ids = [
            item for item in artifact.metadata.get("slide_ids", []) if isinstance(item, str) and item
        ]
        if len(slide_ids) < len(slides):
            raise LarkCliError("missing slide ids for in-place slides update")
        for slide, slide_id in zip(slides, slide_ids):
            self._run(
                [
                    "slides",
                    "+replace-slide",
                    "--as",
                    "user",
                    "--presentation",
                    presentation,
                    "--slide-id",
                    slide_id,
                    "--parts",
                    json.dumps([self._slide_xml(slide)], ensure_ascii=False),
                    "--revision-id",
                    "-1",
                ]
            )
        return artifact.model_copy(
            update={
                "local_path": str(path),
                "status": "updated",
                "summary": "已原地更新 5 页答辩汇报材料。",
                "metadata": {**artifact.metadata, "source_format": "json"},
            }
        )

    def update_canvas(
        self, task_id: str, artifact: ArtifactRef, mermaid: str, task_dir: Path
    ) -> ArtifactRef:
        task_dir.mkdir(parents=True, exist_ok=True)
        path = Path(artifact.local_path) if artifact.local_path else task_dir / "canvas.mmd"
        path.write_text(mermaid, encoding="utf-8")
        whiteboard_token = artifact.metadata.get("whiteboard_token") or artifact.token
        if not isinstance(whiteboard_token, str) or not whiteboard_token:
            raise LarkCliError("missing whiteboard token for in-place update")
        self._run(
            [
                "whiteboard",
                "+update",
                "--as",
                "user",
                "--whiteboard-token",
                whiteboard_token,
                "--source",
                f"@{path.as_posix()}",
                "--input_format",
                "mermaid",
                "--idempotent-token",
                f"agentpilot-{uuid.uuid4().hex[:16]}",
                "--overwrite",
                "--yes",
            ]
        )
        return artifact.model_copy(
            update={
                "local_path": str(path),
                "status": "updated",
                "summary": "已原地更新 Agent 编排架构画板。",
                "metadata": {
                    **artifact.metadata,
                    "source_format": "mermaid",
                    "whiteboard_token": whiteboard_token,
                },
            }
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
        metadata: dict[str, Any] | None = None,
    ) -> ArtifactRef:
        url = _first_result_value(
            result,
            "url",
            "document_url",
            "presentation_url",
            "share_url",
        ) or fallback_url
        token = _first_result_value(
            result,
            "token",
            "document_id",
            "xml_presentation_id",
            "presentation_id",
        )
        return ArtifactRef(
            artifact_id=f"{task_id}-{kind}",
            kind=kind,  # type: ignore[arg-type]
            title=title,
            url=url,
            token=token,
            local_path=str(local_path),
            status="dry_run" if self.dry_run else "created",
            summary=summary,
            metadata=metadata or {},
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

    def _drive_meta_url(self, token: str, doc_type: str) -> str | None:
        try:
            result = self._run(
                [
                    "drive",
                    "metas",
                    "batch_query",
                    "--as",
                    "bot",
                    "--data",
                    json.dumps(
                        {
                            "request_docs": [
                                {"doc_token": token, "doc_type": doc_type},
                            ],
                            "with_url": True,
                        },
                        ensure_ascii=False,
                    ),
                ]
            )
        except LarkCliError:
            return None
        return _first_result_value(result, "url")


def _escape_xml(value: str) -> str:
    return (
        value.replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace('"', "&quot;")
    )


def _write_whiteboard_doc_seed(task_dir: Path, title: str) -> Path:
    path = task_dir / "canvas_seed.md"
    path.write_text(
        f"# {title}\n\n<whiteboard type=\"blank\"></whiteboard>",
        encoding="utf-8",
    )
    return path


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


def _first_result_value(result: dict[str, Any], *keys: str) -> str | None:
    for node in _walk_dicts(result):
        for key in keys:
            value = node.get(key)
            if isinstance(value, str) and value:
                return value
    return None


def _extract_whiteboard_token(result: dict[str, Any]) -> str | None:
    for node in _walk_dicts(result):
        block_type = str(node.get("block_type") or node.get("type") or "").lower()
        if "whiteboard" in block_type:
            token = node.get("block_token") or node.get("token")
            if isinstance(token, str) and token:
                return token
    return None


def _extract_slide_ids(result: dict[str, Any]) -> list[str]:
    slide_ids: list[str] = []
    for node in _walk_dicts(result):
        for key in ("slide_id", "page_id", "id"):
            value = node.get(key)
            if isinstance(value, str) and value and value not in slide_ids:
                slide_ids.append(value)
    return slide_ids


def _is_fallback_url(url: str | None) -> bool:
    return not url or "dry-run.feishu.local" in url or "fake.feishu.local" in url


def _walk_dicts(value: Any):
    if isinstance(value, dict):
        yield value
        for item in value.values():
            yield from _walk_dicts(item)
    elif isinstance(value, list):
        for item in value:
            yield from _walk_dicts(item)


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
    node_prefix = _node_cli_prefix_from_npm_shim(path)
    if node_prefix:
        return node_prefix
    lower_path = path.lower()
    if lower_path.endswith((".cmd", ".bat")):
        powershell_script = Path(path).with_suffix(".ps1")
        if powershell_script.exists():
            return _powershell_file_prefix(str(powershell_script))
    if lower_path.endswith(".ps1"):
        return _powershell_file_prefix(path)
    return [path]


def _node_cli_prefix_from_npm_shim(path: str) -> list[str] | None:
    shim_dir = Path(path).parent
    run_js = shim_dir / "node_modules" / "@larksuite" / "cli" / "scripts" / "run.js"
    if not run_js.exists():
        return None
    node_exe = shim_dir.parent / "node.exe"
    node_command = str(node_exe) if node_exe.exists() else "node"
    return [node_command, str(run_js)]


def _powershell_file_prefix(path: str) -> list[str]:
    return [
        "powershell.exe",
        "-NoProfile",
        "-ExecutionPolicy",
        "Bypass",
        "-File",
        path,
    ]
