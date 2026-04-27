from __future__ import annotations

from pathlib import Path
from typing import Any, Literal, Protocol

from app.integrations.feishu_mcp_client import FeishuMcpClient, McpToolInfo, sanitize_text
from app.integrations.lark_client import LarkClient
from app.schemas.agent_pilot import ArtifactRef, ToolCallPlan, ToolExecutionRecord, utc_now


class UnsupportedCapabilityError(RuntimeError):
    pass


class FeishuToolAdapter(Protocol):
    name: str

    def execute_artifact(
        self,
        call: ToolCallPlan,
        *,
        task_id: str,
        title: str,
        content: object,
        task_dir: Path,
    ) -> ArtifactRef:
        ...


class FeishuMcpToolAdapter:
    name = "mcp"

    def __init__(
        self,
        *,
        mode: Literal["off", "dry_run", "real"] = "off",
        client: FeishuMcpClient | None = None,
        secrets: list[str] | None = None,
        use_uat: bool = True,
    ):
        self.mode = mode
        self.client = client
        self.secrets = secrets or []
        self.use_uat = use_uat

    def execute_artifact(
        self,
        call: ToolCallPlan,
        *,
        task_id: str,
        title: str,
        content: object,
        task_dir: Path,
    ) -> ArtifactRef:
        if self.mode == "off":
            raise UnsupportedCapabilityError(f"MCP adapter does not support {call.capability}.")
        if call.capability != "create_doc":
            raise UnsupportedCapabilityError(f"MCP adapter only supports create_doc, not {call.capability}.")
        if not self.client:
            raise UnsupportedCapabilityError("MCP client is not configured.")

        try:
            tool = _find_doc_import_tool(self.client.list_tools())
            arguments = _build_doc_import_arguments(
                tool,
                title=title,
                content=str(content),
                use_uat=self.use_uat,
            )
            if self.mode == "dry_run":
                return ArtifactRef(
                    artifact_id=f"{task_id}-{call.capability}-mcp-dry-run",
                    kind="doc",
                    title=title,
                    status="dry_run",
                    summary=f"MCP dry-run accepted {tool.name}; payload shape is valid.",
                )

            result = self.client.call_tool(tool.name, arguments)
            tool_error = _mcp_tool_error(result.data)
            if tool_error:
                raise UnsupportedCapabilityError(sanitize_text(tool_error, secrets=self.secrets))
            url = _extract_first(result.data, ["url", "document_url", "doc_url", "link"])
            token = _extract_first(result.data, ["token", "document_id", "document_token", "file_token", "obj_token"])
            if not url and not token:
                raise UnsupportedCapabilityError("MCP doc import returned no url or token.")
            return ArtifactRef(
                artifact_id=f"{task_id}-doc-mcp",
                kind="doc",
                title=title,
                url=url,
                token=token,
                status="created",
                summary="已通过官方飞书 MCP 导入创建参赛方案文档。",
            )
        except UnsupportedCapabilityError:
            raise
        except Exception as exc:
            raise UnsupportedCapabilityError(sanitize_text(str(exc), secrets=self.secrets)) from exc


class LarkCliToolAdapter:
    name = "lark_cli"

    def __init__(self, lark_client: LarkClient):
        self.lark_client = lark_client

    def execute_artifact(
        self,
        call: ToolCallPlan,
        *,
        task_id: str,
        title: str,
        content: object,
        task_dir: Path,
    ) -> ArtifactRef:
        if call.capability == "create_doc":
            return self.lark_client.create_doc(task_id, title, str(content), task_dir)
        if call.capability == "create_slides":
            if not isinstance(content, list):
                raise TypeError("Slides content must be a list of slide dictionaries.")
            return self.lark_client.create_slides(task_id, title, content, task_dir)
        if call.capability == "create_canvas":
            return self.lark_client.create_canvas(task_id, title, str(content), task_dir)
        raise UnsupportedCapabilityError(f"lark-cli adapter does not support {call.capability}.")


class FeishuToolLayer:
    def __init__(self, adapters: dict[str, FeishuToolAdapter]):
        self.adapters = adapters

    def execute_artifact(
        self,
        call: ToolCallPlan,
        *,
        task_id: str,
        title: str,
        content: object,
        task_dir: Path,
    ) -> tuple[ArtifactRef, list[ToolExecutionRecord]]:
        records: list[ToolExecutionRecord] = []
        adapter_names = _adapter_order(call)
        last_error: Exception | None = None

        for index, adapter_name in enumerate(adapter_names):
            adapter = self.adapters.get(adapter_name)
            if adapter is None:
                last_error = UnsupportedCapabilityError(f"Adapter {adapter_name} is not configured.")
                records.append(_record(call.id, adapter_name, "fallback", error=str(last_error)))
                continue

            started_at = utc_now()
            try:
                artifact = adapter.execute_artifact(
                    call,
                    task_id=task_id,
                    title=title,
                    content=content,
                    task_dir=task_dir,
                )
            except Exception as exc:
                last_error = exc
                status = "fallback" if index < len(adapter_names) - 1 else "failed"
                records.append(
                    ToolExecutionRecord(
                        call_id=call.id,
                        adapter=adapter_name,
                        status=status,
                        started_at=started_at,
                        finished_at=utc_now(),
                        error=str(exc),
                    )
                )
                continue

            records.append(
                ToolExecutionRecord(
                    call_id=call.id,
                    adapter=adapter_name,
                    status="succeeded",
                    started_at=started_at,
                    finished_at=utc_now(),
                    output_ref=artifact,
                )
            )
            return artifact, records

        raise RuntimeError(f"All adapters failed for {call.capability}: {last_error}")


def _adapter_order(call: ToolCallPlan) -> list[str]:
    ordered = [call.preferred_adapter, *call.fallback_adapters]
    result: list[str] = []
    for item in ordered:
        if item not in result:
            result.append(item)
    return result


def _record(call_id: str, adapter: str, status: str, *, error: str | None = None) -> ToolExecutionRecord:
    now = utc_now()
    return ToolExecutionRecord(
        call_id=call_id,
        adapter=adapter,
        status=status,  # type: ignore[arg-type]
        started_at=now,
        finished_at=now,
        error=error,
    )


def _artifact_kind_for_capability(capability: str):
    if capability == "create_doc":
        return "doc"
    if capability == "create_slides":
        return "slides"
    if capability == "create_canvas":
        return "canvas"
    raise UnsupportedCapabilityError(f"Unknown artifact capability {capability}.")


def _find_doc_import_tool(tools: list[McpToolInfo]) -> McpToolInfo:
    for tool in tools:
        if _canonical_tool_name(tool.name) == "docx_builtin_import":
            return tool
    raise UnsupportedCapabilityError("MCP tool docx_builtin_import is not available.")


def _canonical_tool_name(name: str) -> str:
    return name.replace(".", "_").replace("-", "_").lower()


def _build_doc_import_arguments(
    tool: McpToolInfo,
    *,
    title: str,
    content: str,
    use_uat: bool,
) -> dict[str, Any]:
    properties = tool.input_schema.get("properties")
    if not isinstance(properties, dict):
        raise UnsupportedCapabilityError("MCP doc import schema is not recognizable.")

    if "title" in properties and "content" in properties:
        arguments: dict[str, Any] = {
            "title": title,
            "content": content,
        }
        if "format" in properties:
            arguments["format"] = "markdown"
        return arguments

    data_property = properties.get("data")
    data_properties = data_property.get("properties") if isinstance(data_property, dict) else None
    if isinstance(data_properties, dict) and "markdown" in data_properties:
        arguments = {
            "data": {
                "markdown": content,
                "file_name": _truncate_file_name(title, data_properties),
            }
        }
        if "useUAT" in properties:
            arguments["useUAT"] = use_uat
        return arguments

    raise UnsupportedCapabilityError("MCP doc import schema is not recognizable.")


def _truncate_file_name(title: str, data_properties: dict[str, Any]) -> str:
    file_name = title.strip() or "Agent-Pilot"
    file_name_schema = data_properties.get("file_name")
    max_length = None
    if isinstance(file_name_schema, dict):
        raw_max_length = file_name_schema.get("maxLength")
        if isinstance(raw_max_length, int) and raw_max_length > 0:
            max_length = raw_max_length
    if max_length and len(file_name) > max_length:
        return file_name[:max_length]
    return file_name


def _extract_first(data: dict[str, Any], keys: list[str]) -> str | None:
    for key in keys:
        value = _deep_get(data, key)
        if isinstance(value, str) and value.strip():
            return value.strip()
    return None


def _mcp_tool_error(data: dict[str, Any]) -> str | None:
    error_message = _deep_get(data, "errorMessage") or _deep_get(data, "error")
    if not isinstance(error_message, str) or not error_message.strip():
        code = _deep_get(data, "code")
        message = _deep_get(data, "msg") or _deep_get(data, "message")
        if isinstance(code, int) and code != 0 and isinstance(message, str) and message.strip():
            return f"{code}: {message.strip()}"
        return None
    instruction = _deep_get(data, "instruction")
    if isinstance(instruction, str) and instruction.strip():
        return f"{error_message.strip()} {instruction.strip()}"
    return error_message.strip()


def _deep_get(data: dict[str, Any], key: str) -> Any:
    if key in data:
        return data[key]
    for value in data.values():
        if isinstance(value, dict):
            nested = _deep_get(value, key)
            if nested is not None:
                return nested
    return None
