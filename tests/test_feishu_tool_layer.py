from pathlib import Path
import time

from app.integrations.fake_lark_client import FakeLarkClient
from app.integrations.feishu_mcp_client import McpToolInfo, McpToolResult
from app.schemas.agent_pilot import ArtifactRef
from app.schemas.agent_pilot import ToolCallPlan
from app.services.feishu_tool_layer import (
    FeishuMcpToolAdapter,
    FeishuToolLayer,
    LarkCliToolAdapter,
    UnsupportedCapabilityError,
)


def _doc_call(preferred_adapter: str = "mcp") -> ToolCallPlan:
    return ToolCallPlan(
        id="doc-1",
        scenario="C",
        capability="create_doc",
        preferred_adapter=preferred_adapter,
        fallback_adapters=["lark_cli", "fake"],
        inputs={"title": "Agent-Pilot 参赛方案"},
        expected_output="飞书文档链接",
        user_visible_reason="沉淀参赛方案。",
    )


def _slides_call() -> ToolCallPlan:
    return ToolCallPlan(
        id="slides-1",
        scenario="D",
        capability="create_slides",
        preferred_adapter="mcp",
        fallback_adapters=["lark_cli", "fake"],
        inputs={"title": "Agent-Pilot 5 页答辩汇报材料"},
        expected_output="飞书幻灯片链接",
        user_visible_reason="生成答辩材料。",
    )


class FakeMcpClient:
    def __init__(
        self,
        *,
        tools: list[McpToolInfo] | None = None,
        result: McpToolResult | None = None,
        error: Exception | None = None,
    ):
        self.tools = tools or []
        self.result = result or McpToolResult(data={})
        self.error = error
        self.calls: list[tuple[str, dict]] = []

    def list_tools(self) -> list[McpToolInfo]:
        return self.tools

    def call_tool(self, name: str, arguments: dict) -> McpToolResult:
        self.calls.append((name, arguments))
        if self.error:
            raise self.error
        return self.result


def _import_tool(schema: dict | None = None) -> McpToolInfo:
    return McpToolInfo(
        name="docx_builtin_import",
        input_schema=schema
        or {
            "type": "object",
            "properties": {
                "title": {"type": "string"},
                "content": {"type": "string"},
                "format": {"type": "string"},
            },
        },
    )


def test_mcp_adapter_reports_unsupported_capability():
    adapter = FeishuMcpToolAdapter(mode="off")

    try:
        adapter.execute_artifact(
            _doc_call(),
            task_id="task-1",
            title="Agent-Pilot 参赛方案",
            content="# doc",
            task_dir=Path("."),
        )
    except UnsupportedCapabilityError as exc:
        assert "create_doc" in str(exc)
    else:
        raise AssertionError("unsupported MCP capability should raise")


def test_mcp_adapter_dry_run_reads_manifest_without_calling_tool(tmp_path):
    client = FakeMcpClient(tools=[_import_tool()])
    adapter = FeishuMcpToolAdapter(mode="dry_run", client=client)

    artifact = adapter.execute_artifact(
        _doc_call(),
        task_id="task-1",
        title="Agent-Pilot 参赛方案",
        content="# doc",
        task_dir=tmp_path,
    )

    assert artifact.kind == "doc"
    assert artifact.status == "dry_run"
    assert client.calls == []


def test_mcp_adapter_real_doc_import_returns_created_artifact(tmp_path):
    client = FakeMcpClient(
        tools=[_import_tool()],
        result=McpToolResult(data={"url": "https://example.feishu.cn/docx/abc", "token": "doc-token"}),
    )
    adapter = FeishuMcpToolAdapter(mode="real", client=client)

    artifact = adapter.execute_artifact(
        _doc_call(),
        task_id="task-1",
        title="Agent-Pilot 参赛方案",
        content="# doc",
        task_dir=tmp_path,
    )

    assert artifact.kind == "doc"
    assert artifact.status == "created"
    assert artifact.url == "https://example.feishu.cn/docx/abc"
    assert artifact.token == "doc-token"
    assert client.calls == [
        (
            "docx_builtin_import",
            {"title": "Agent-Pilot 参赛方案", "content": "# doc", "format": "markdown"},
        )
    ]


def test_mcp_adapter_supports_official_docx_import_data_schema(tmp_path):
    client = FakeMcpClient(
        tools=[
            _import_tool(
                {
                    "type": "object",
                    "properties": {
                        "data": {
                            "type": "object",
                            "properties": {
                                "markdown": {"type": "string"},
                                "file_name": {"type": "string", "maxLength": 27},
                            },
                            "required": ["markdown"],
                        },
                        "useUAT": {"type": "boolean"},
                    },
                    "required": ["data"],
                }
            )
        ],
        result=McpToolResult(data={"data": {"url": "https://example.feishu.cn/docx/abc", "token": "doc-token"}}),
    )
    adapter = FeishuMcpToolAdapter(mode="real", client=client)

    artifact = adapter.execute_artifact(
        _doc_call(),
        task_id="task-1",
        title="Agent-Pilot 参赛方案",
        content="# doc",
        task_dir=tmp_path,
    )

    assert artifact.url == "https://example.feishu.cn/docx/abc"
    assert client.calls == [
        (
            "docx_builtin_import",
            {
                "data": {
                    "markdown": "# doc",
                    "file_name": "Agent-Pilot 参赛方案",
                },
                "useUAT": True,
            },
        )
    ]


def test_mcp_adapter_can_disable_user_access_token_for_official_import_schema(tmp_path):
    client = FakeMcpClient(
        tools=[
            _import_tool(
                {
                    "type": "object",
                    "properties": {
                        "data": {
                            "type": "object",
                            "properties": {
                                "markdown": {"type": "string"},
                                "file_name": {"type": "string"},
                            },
                        },
                        "useUAT": {"type": "boolean"},
                    },
                }
            )
        ],
        result=McpToolResult(data={"url": "https://example.feishu.cn/docx/abc"}),
    )
    adapter = FeishuMcpToolAdapter(mode="real", client=client, use_uat=False)

    adapter.execute_artifact(
        _doc_call(),
        task_id="task-1",
        title="Agent-Pilot 参赛方案",
        content="# doc",
        task_dir=tmp_path,
    )

    assert client.calls[0][1]["useUAT"] is False


def test_mcp_adapter_rejects_unknown_import_schema(tmp_path):
    client = FakeMcpClient(
        tools=[
            _import_tool(
                {
                    "type": "object",
                    "properties": {"file_path": {"type": "string"}},
                }
            )
        ]
    )
    adapter = FeishuMcpToolAdapter(mode="real", client=client)

    try:
        adapter.execute_artifact(
            _doc_call(),
            task_id="task-1",
            title="Agent-Pilot 参赛方案",
            content="# doc",
            task_dir=tmp_path,
        )
    except UnsupportedCapabilityError as exc:
        assert "schema" in str(exc)
    else:
        raise AssertionError("unrecognized MCP import schema should raise")


def test_mcp_adapter_surfaces_tool_error_message(tmp_path):
    client = FakeMcpClient(
        tools=[_import_tool()],
        result=McpToolResult(
            data={
                "errorMessage": "Current user_access_token is invalid or expired",
                "instruction": "Please open the authorization URL.",
            }
        ),
    )
    adapter = FeishuMcpToolAdapter(mode="real", client=client)

    try:
        adapter.execute_artifact(
            _doc_call(),
            task_id="task-1",
            title="Agent-Pilot 参赛方案",
            content="# doc",
            task_dir=tmp_path,
        )
    except UnsupportedCapabilityError as exc:
        assert "user_access_token" in str(exc)
    else:
        raise AssertionError("MCP tool errors should raise")


def test_mcp_adapter_surfaces_nonzero_code_message(tmp_path):
    client = FakeMcpClient(
        tools=[_import_tool()],
        result=McpToolResult(
            data={
                "code": 99991672,
                "msg": "Access denied. One of the following scopes is required: [docs:doc].",
            }
        ),
    )
    adapter = FeishuMcpToolAdapter(mode="real", client=client)

    try:
        adapter.execute_artifact(
            _doc_call(),
            task_id="task-1",
            title="Agent-Pilot 参赛方案",
            content="# doc",
            task_dir=tmp_path,
        )
    except UnsupportedCapabilityError as exc:
        assert "99991672" in str(exc)
        assert "docs:doc" in str(exc)
    else:
        raise AssertionError("MCP nonzero code should raise")


def test_mcp_adapter_real_only_supports_doc_import(tmp_path):
    adapter = FeishuMcpToolAdapter(mode="real", client=FakeMcpClient(tools=[_import_tool()]))

    try:
        adapter.execute_artifact(
            _slides_call(),
            task_id="task-1",
            title="Agent-Pilot 5 页答辩汇报材料",
            content=[],
            task_dir=tmp_path,
        )
    except UnsupportedCapabilityError as exc:
        assert "create_slides" in str(exc)
    else:
        raise AssertionError("MCP should not execute slides")


def test_tool_layer_records_sanitized_mcp_error_and_falls_back(tmp_path):
    fake_lark = FakeLarkClient()
    layer = FeishuToolLayer(
        adapters={
            "mcp": FeishuMcpToolAdapter(
                mode="real",
                client=FakeMcpClient(
                    tools=[_import_tool()],
                    error=RuntimeError("permission denied for secret-value"),
                ),
                secrets=["secret-value"],
            ),
            "lark_cli": LarkCliToolAdapter(fake_lark),
        }
    )

    artifact, records = layer.execute_artifact(
        _doc_call(),
        task_id="task-1",
        title="Agent-Pilot 参赛方案",
        content="# doc",
        task_dir=tmp_path,
    )

    assert artifact.status == "fake"
    assert records[0].adapter == "mcp"
    assert records[0].status == "fallback"
    assert records[0].error is not None
    assert "secret-value" not in records[0].error


def test_tool_layer_falls_back_from_mcp_to_lark_cli(tmp_path):
    fake_lark = FakeLarkClient()
    layer = FeishuToolLayer(
        adapters={
            "mcp": FeishuMcpToolAdapter(mode="off"),
            "lark_cli": LarkCliToolAdapter(fake_lark),
        }
    )

    artifact, records = layer.execute_artifact(
        _doc_call(),
        task_id="task-1",
        title="Agent-Pilot 参赛方案",
        content="# doc",
        task_dir=tmp_path,
    )

    assert artifact.kind == "doc"
    assert artifact.status == "fake"
    assert [record.adapter for record in records] == ["mcp", "lark_cli"]
    assert records[0].status == "fallback"
    assert records[1].status == "succeeded"


def test_tool_layer_uses_fake_when_cli_fails(tmp_path):
    class FailingClient(FakeLarkClient):
        def create_doc(self, task_id: str, title: str, content: str, task_dir: Path):
            raise RuntimeError("permission denied")

    layer = FeishuToolLayer(
        adapters={
            "lark_cli": LarkCliToolAdapter(FailingClient()),
            "fake": LarkCliToolAdapter(FakeLarkClient()),
        }
    )

    artifact, records = layer.execute_artifact(
        _doc_call(preferred_adapter="lark_cli"),
        task_id="task-1",
        title="Agent-Pilot 参赛方案",
        content="# doc",
        task_dir=tmp_path,
    )

    assert artifact.url == "https://fake.feishu.local/doc/task-1"
    assert [record.status for record in records] == ["fallback", "succeeded"]


def test_tool_layer_times_out_stuck_adapter_and_uses_fallback(tmp_path):
    class StuckAdapter:
        name = "mcp"

        def execute_artifact(self, call, *, task_id, title, content, task_dir):
            time.sleep(0.2)
            return ArtifactRef(
                artifact_id="late-doc",
                kind="doc",
                title=title,
                url="https://late.example/doc",
                status="created",
            )

    layer = FeishuToolLayer(
        adapters={
            "mcp": StuckAdapter(),
            "fake": LarkCliToolAdapter(FakeLarkClient()),
        },
        adapter_timeout_seconds=0.03,
    )
    started = time.perf_counter()

    artifact, records = layer.execute_artifact(
        _doc_call(preferred_adapter="mcp"),
        task_id="task-1",
        title="Agent-Pilot 鍙傝禌鏂规",
        content="# doc",
        task_dir=tmp_path,
    )

    assert time.perf_counter() - started < 0.15
    assert artifact.url == "https://fake.feishu.local/doc/task-1"
    assert records[0].adapter == "mcp"
    assert records[0].status == "fallback"
    assert "timed out" in records[0].error
    assert records[-1].adapter == "fake"
    assert records[-1].status == "succeeded"
