from __future__ import annotations

import asyncio
import json
import re
from dataclasses import dataclass, field
from typing import Any, Literal, Protocol


DEFAULT_FEISHU_MCP_TOOLS = [
    "docx.builtin.import",
    "docx.v1.document.rawContent",
    "docx.builtin.search",
]


@dataclass(frozen=True)
class McpToolInfo:
    name: str
    input_schema: dict[str, Any] = field(default_factory=dict)
    description: str = ""


@dataclass(frozen=True)
class McpToolResult:
    data: dict[str, Any] = field(default_factory=dict)
    text: str = ""
    raw: Any | None = None


class FeishuMcpClient(Protocol):
    def list_tools(self) -> list[McpToolInfo]:
        ...

    def call_tool(self, name: str, arguments: dict[str, Any]) -> McpToolResult:
        ...


class SubprocessFeishuMcpClient:
    def __init__(
        self,
        *,
        app_id: str,
        app_secret: str,
        domain: str = "https://open.feishu.cn",
        tools: list[str] | None = None,
        timeout_seconds: float = 20.0,
        token_mode: Literal["auto", "user_access_token", "tenant_access_token"] = "user_access_token",
    ):
        self.app_id = app_id
        self.app_secret = app_secret
        self.domain = domain
        self.tools = tools or DEFAULT_FEISHU_MCP_TOOLS
        self.timeout_seconds = timeout_seconds
        self.token_mode = token_mode

    def build_command(self) -> tuple[str, list[str]]:
        args = [
            "-y",
            "@larksuiteoapi/lark-mcp",
            "mcp",
            "-a",
            self.app_id,
            "-s",
            self.app_secret,
            "-d",
            self.domain,
            "-t",
            ",".join(self.tools),
            "-c",
            "snake",
            "-l",
            "zh",
            "--token-mode",
            self.token_mode,
        ]
        if self.token_mode != "tenant_access_token":
            args.append("--oauth")
        return ("npx", args)

    def safe_command_for_log(self) -> str:
        command, args = self.build_command()
        return sanitize_text(" ".join([command, *args]), secrets=[self.app_secret])

    def list_tools(self) -> list[McpToolInfo]:
        try:
            return self._run(self._list_tools_async())
        except Exception as exc:
            raise RuntimeError(self.sanitize_error(exc)) from exc

    def call_tool(self, name: str, arguments: dict[str, Any]) -> McpToolResult:
        try:
            return self._run(self._call_tool_async(name, arguments))
        except Exception as exc:
            raise RuntimeError(self.sanitize_error(exc)) from exc

    def sanitize_error(self, exc: Exception) -> str:
        return sanitize_text(str(exc), secrets=[self.app_secret])

    def _run(self, coro: Any) -> Any:
        return asyncio.run(asyncio.wait_for(coro, timeout=self.timeout_seconds))

    async def _list_tools_async(self) -> list[McpToolInfo]:
        async def _operation(client_session: Any) -> list[McpToolInfo]:
            result = await client_session.list_tools()
            tools = getattr(result, "tools", result)
            return [_tool_info_from_raw(tool) for tool in tools]

        return await self._with_session(_operation)

    async def _call_tool_async(self, name: str, arguments: dict[str, Any]) -> McpToolResult:
        async def _operation(client_session: Any) -> McpToolResult:
            result = await client_session.call_tool(name, arguments)
            return _tool_result_from_raw(result)

        return await self._with_session(_operation)

    async def _with_session(self, operation: Any) -> Any:
        try:
            from mcp import ClientSession, StdioServerParameters
            from mcp.client.stdio import stdio_client
        except ImportError as exc:
            raise RuntimeError(
                "Python MCP SDK is not installed. Install requirements.txt before enabling FEISHU_MCP_MODE."
            ) from exc

        command, args = self.build_command()
        parameters = StdioServerParameters(command=command, args=args)
        async with stdio_client(parameters) as (read_stream, write_stream):
            async with ClientSession(read_stream, write_stream) as session:
                await session.initialize()
                return await operation(session)


def sanitize_text(text: str, *, secrets: list[str] | tuple[str, ...] = ()) -> str:
    sanitized = text
    for secret in secrets:
        if secret:
            sanitized = sanitized.replace(secret, "***")
    sanitized = re.sub(r"bearer\s+[A-Za-z0-9._-]+", "bearer ***", sanitized, flags=re.IGNORECASE)
    sanitized = re.sub(r"(user_access_token=)[A-Za-z0-9._-]+", r"\1***", sanitized, flags=re.IGNORECASE)
    return sanitized


def _tool_info_from_raw(raw: Any) -> McpToolInfo:
    if isinstance(raw, dict):
        return McpToolInfo(
            name=str(raw.get("name") or ""),
            input_schema=dict(raw.get("inputSchema") or raw.get("input_schema") or {}),
            description=str(raw.get("description") or ""),
        )
    return McpToolInfo(
        name=str(getattr(raw, "name", "")),
        input_schema=dict(getattr(raw, "inputSchema", None) or getattr(raw, "input_schema", None) or {}),
        description=str(getattr(raw, "description", "") or ""),
    )


def _tool_result_from_raw(raw: Any) -> McpToolResult:
    data: dict[str, Any] = {}
    text_parts: list[str] = []
    structured = getattr(raw, "structuredContent", None) or getattr(raw, "structured_content", None)
    if isinstance(structured, dict):
        data.update(structured)
    if isinstance(raw, dict):
        data.update(raw)
    for item in getattr(raw, "content", []) or []:
        item_text = getattr(item, "text", None)
        if isinstance(item_text, str):
            text_parts.append(item_text)
            try:
                parsed = json.loads(item_text)
            except json.JSONDecodeError:
                continue
            if isinstance(parsed, dict):
                data.update(parsed)
    return McpToolResult(data=data, text="\n".join(text_parts), raw=raw)
