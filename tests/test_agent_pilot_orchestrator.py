from app.integrations.fake_lark_client import FakeLarkClient
from app.integrations.feishu_mcp_client import McpToolInfo, McpToolResult
from app.schemas.agent_pilot import AgentPilotCommand, TaskCreateRequest
from app.services.feishu_tool_layer import FeishuMcpToolAdapter, FeishuToolLayer, LarkCliToolAdapter
from app.services.orchestrator import AgentPilotOrchestrator
from app.services.state_service import StateService


def _orchestrator(tmp_path):
    return AgentPilotOrchestrator(StateService(tmp_path), FakeLarkClient())


def test_create_task_waits_for_confirmation(tmp_path):
    lark_client = FakeLarkClient()
    orchestrator = AgentPilotOrchestrator(StateService(tmp_path), lark_client)

    response = orchestrator.create_task(
        TaskCreateRequest(message="@Agent 生成参赛方案", chat_id="oc_demo", message_id="om_demo")
    )

    assert response.status == "WAITING_CONFIRMATION"
    assert response.plan is not None
    assert "确认" in response.reply
    assert "已收到需求" in lark_client.sent_messages[0]["text"]
    assert lark_client.sent_messages[0]["type"] == "interactive"
    assert lark_client.sent_messages[-1]["type"] == "update"
    assert lark_client.sent_messages[-1]["text"] == response.reply


def test_create_task_auto_confirm_runs_to_delivery(tmp_path):
    lark_client = FakeLarkClient()
    orchestrator = AgentPilotOrchestrator(
        StateService(tmp_path),
        lark_client,
        auto_confirm=True,
    )

    response = orchestrator.create_task(
        TaskCreateRequest(message="@Agent 生成参赛方案", chat_id="oc_demo", message_id="om_demo")
    )

    assert response.status == "DONE"
    assert {artifact.kind for artifact in response.artifacts} == {"doc", "slides", "canvas"}
    assert any("自动执行模式" in item["text"] for item in lark_client.sent_messages)
    assert "任务已完成" in lark_client.sent_messages[-1]["text"]


def test_create_task_sends_planning_ack_before_planner_returns(tmp_path, monkeypatch):
    from app.services import orchestrator as orchestrator_module
    from app.agents.planner_agent import build_fallback_plan

    lark_client = FakeLarkClient()
    orchestrator = AgentPilotOrchestrator(StateService(tmp_path), lark_client)

    def slow_plan_builder(message: str):
        assert lark_client.sent_messages
        assert "已收到需求" in lark_client.sent_messages[0]["text"]
        return build_fallback_plan(message)

    monkeypatch.setattr(orchestrator_module, "build_agent_plan", slow_plan_builder)

    response = orchestrator.create_task(
        TaskCreateRequest(message="@Agent 生成参赛方案", chat_id="oc_demo", message_id="om_demo")
    )

    assert response.status == "WAITING_CONFIRMATION"


def test_create_task_falls_back_to_text_when_stream_card_fails(tmp_path):
    class NoCardFakeClient(FakeLarkClient):
        def reply_interactive_card(self, message_id: str, text: str) -> dict:
            raise RuntimeError("missing card permission")

    lark_client = NoCardFakeClient()
    orchestrator = AgentPilotOrchestrator(StateService(tmp_path), lark_client)

    response = orchestrator.create_task(
        TaskCreateRequest(message="@Agent 生成参赛方案", chat_id="oc_demo", message_id="om_demo")
    )

    assert response.status == "WAITING_CONFIRMATION"
    assert lark_client.sent_messages[-1]["reply_to_message_id"] == "om_demo"
    assert lark_client.sent_messages[-1]["text"] == response.reply


def test_confirm_generates_three_artifacts(tmp_path):
    orchestrator = _orchestrator(tmp_path)
    created = orchestrator.create_task(TaskCreateRequest(message="生成参赛方案", chat_id="oc_demo"))

    confirmed = orchestrator.confirm_task(created.task_id)

    assert confirmed.status == "DONE"
    assert confirmed.artifact_brief is not None
    assert confirmed.artifact_brief.official_requirement_mapping["A"].startswith("意图入口")
    assert confirmed.tool_executions
    assert {artifact.kind for artifact in confirmed.artifacts} == {"doc", "slides", "canvas"}
    assert (tmp_path / "tasks" / created.task_id / "doc.md").exists()


def test_confirm_prefers_mcp_for_doc_when_mcp_real_is_configured(tmp_path):
    class FakeMcpClient:
        def list_tools(self):
            return [
                McpToolInfo(
                    name="docx_builtin_import",
                    input_schema={
                        "type": "object",
                        "properties": {
                            "title": {"type": "string"},
                            "content": {"type": "string"},
                            "format": {"type": "string"},
                        },
                    },
                )
            ]

        def call_tool(self, name: str, arguments: dict):
            return McpToolResult(
                data={
                    "url": "https://example.feishu.cn/docx/doc-token",
                    "token": "doc-token",
                }
            )

    lark_client = FakeLarkClient()
    tool_layer = FeishuToolLayer(
        {
            "mcp": FeishuMcpToolAdapter(mode="real", client=FakeMcpClient()),
            "lark_cli": LarkCliToolAdapter(lark_client),
            "fake": LarkCliToolAdapter(FakeLarkClient()),
        }
    )
    orchestrator = AgentPilotOrchestrator(
        StateService(tmp_path),
        lark_client,
        tool_layer=tool_layer,
    )
    created = orchestrator.create_task(TaskCreateRequest(message="生成参赛方案", chat_id="oc_demo"))

    confirmed = orchestrator.confirm_task(created.task_id)

    assert confirmed.artifacts[0].kind == "doc"
    assert confirmed.artifacts[0].url == "https://example.feishu.cn/docx/doc-token"
    assert confirmed.tool_executions[0].adapter == "mcp"
    assert confirmed.tool_executions[0].status == "succeeded"


def test_revise_records_revision(tmp_path):
    orchestrator = _orchestrator(tmp_path)
    created = orchestrator.create_task(TaskCreateRequest(message="生成参赛方案", chat_id="oc_demo"))
    orchestrator.confirm_task(created.task_id)

    revised = orchestrator.revise_task(created.task_id, "修改：PPT 更突出工程实现")

    assert revised.status == "DONE"
    assert revised.revisions[0].target_artifacts == ["slides"]
    assert "已处理修改" in revised.reply


def test_reset_command_clears_active_chat_task(tmp_path):
    lark_client = FakeLarkClient()
    state_service = StateService(tmp_path)
    orchestrator = AgentPilotOrchestrator(state_service, lark_client)
    created = orchestrator.create_task(TaskCreateRequest(message="生成参赛方案", chat_id="oc_demo"))

    assert state_service.get_active_task_id("oc_demo") == created.task_id

    response = orchestrator.handle_command(
        AgentPilotCommand(
            type="reset",
            text="/reset",
            chat_id="oc_demo",
            message_id="om_demo",
        )
    )

    assert response is None
    assert state_service.get_active_task_id("oc_demo") is None
    assert "已重置" in lark_client.sent_messages[-1]["text"]


def test_help_command_replies_with_available_commands(tmp_path):
    lark_client = FakeLarkClient()
    orchestrator = AgentPilotOrchestrator(StateService(tmp_path), lark_client)

    response = orchestrator.handle_command(
        AgentPilotCommand(
            type="help",
            text="/help",
            chat_id="oc_demo",
            message_id="om_demo",
        )
    )

    assert response is None
    assert "/reset" in lark_client.sent_messages[-1]["text"]
    assert "确认" in lark_client.sent_messages[-1]["text"]


def test_followup_command_without_active_task_gets_helpful_reply(tmp_path):
    lark_client = FakeLarkClient()
    orchestrator = AgentPilotOrchestrator(StateService(tmp_path), lark_client)

    response = orchestrator.handle_command(
        AgentPilotCommand(
            type="confirm",
            text="确认",
            chat_id="oc_demo",
            message_id="om_demo",
        )
    )

    assert response is None
    assert "当前没有活跃任务" in lark_client.sent_messages[-1]["text"]
