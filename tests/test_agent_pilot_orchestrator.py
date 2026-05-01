import json
import re
import time

import pytest

from app.integrations.fake_lark_client import FakeLarkClient
from app.integrations.feishu_mcp_client import McpToolInfo, McpToolResult
from app.schemas.agent_pilot import AgentPilotCommand, TaskCreateRequest
from app.services.feishu_tool_layer import FeishuMcpToolAdapter, FeishuToolLayer, LarkCliToolAdapter
from app.services.orchestrator import AgentPilotOrchestrator
from app.services.state_service import StateService
from app.services.task_message_service import TaskMessageService


class _FakeRevisionLLM:
    def __init__(self, **kwargs):
        pass

    def invoke(self, messages):
        # Return content that fails all artifact-type validations so keyword
        # fallback is always used in orchestrator tests.
        return json.dumps({"content": "fallback-trigger", "change_summary": "触发兜底"})


@pytest.fixture(autouse=True)
def _patch_revision_llm(monkeypatch):
    """Avoid real LLM calls in build_llm_revision_content across all orchestrator tests."""
    from app.agents import artifact_revision_agent

    monkeypatch.setattr(artifact_revision_agent, "JobResearchLLM", _FakeRevisionLLM)


def _orchestrator(tmp_path):
    return AgentPilotOrchestrator(StateService(tmp_path), FakeLarkClient())


class RecordingFakeLarkClient(FakeLarkClient):
    def __init__(self):
        super().__init__()
        self.created_artifacts = {"doc": 0, "slides": 0, "canvas": 0}
        self.updated_artifacts = {"doc": 0, "slides": 0, "canvas": 0}

    def create_doc(self, *args, **kwargs):
        self.created_artifacts["doc"] += 1
        return super().create_doc(*args, **kwargs)

    def create_slides(self, *args, **kwargs):
        self.created_artifacts["slides"] += 1
        return super().create_slides(*args, **kwargs)

    def create_canvas(self, *args, **kwargs):
        self.created_artifacts["canvas"] += 1
        return super().create_canvas(*args, **kwargs)

    def update_doc(self, *args, **kwargs):
        self.updated_artifacts["doc"] += 1
        return super().update_doc(*args, **kwargs)

    def update_slides(self, *args, **kwargs):
        self.updated_artifacts["slides"] += 1
        return super().update_slides(*args, **kwargs)

    def update_canvas(self, *args, **kwargs):
        self.updated_artifacts["canvas"] += 1
        return super().update_canvas(*args, **kwargs)


def _artifact_by_kind(response, kind):
    return next(artifact for artifact in response.artifacts if artifact.kind == kind)


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


def test_background_auto_confirm_returns_before_slow_artifact_generation(tmp_path):
    class SlowDocLarkClient(RecordingFakeLarkClient):
        def create_doc(self, *args, **kwargs):
            time.sleep(0.2)
            return super().create_doc(*args, **kwargs)

    lark_client = SlowDocLarkClient()
    orchestrator = AgentPilotOrchestrator(
        StateService(tmp_path),
        lark_client,
        auto_confirm=True,
        background_auto_confirm=True,
    )
    started = time.perf_counter()

    response = orchestrator.create_task(
        TaskCreateRequest(message="@Agent 鐢熸垚鍙傝禌鏂规", chat_id="oc_demo", message_id="om_demo")
    )

    assert time.perf_counter() - started < 0.15
    assert response.task_id
    assert response.status in {"WAITING_CONFIRMATION", "DOC_GENERATING"}

    progress = orchestrator.get_progress(response.task_id)
    assert progress.status in {
        "WAITING_CONFIRMATION",
        "DOC_GENERATING",
        "PRESENTATION_GENERATING",
        "CANVAS_GENERATING",
        "DELIVERING",
        "DONE",
    }

    deadline = time.perf_counter() + 2
    final = progress
    while time.perf_counter() < deadline:
        final = orchestrator.get_task(response.task_id)
        if final.status == "DONE":
            break
        time.sleep(0.02)

    assert final.status == "DONE"
    assert {artifact.kind for artifact in final.artifacts} == {"doc", "slides", "canvas"}


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


def test_doc_edit_without_revision_prefix_updates_only_doc(tmp_path):
    lark_client = RecordingFakeLarkClient()
    state_service = StateService(tmp_path)
    orchestrator = AgentPilotOrchestrator(state_service, lark_client)
    created = orchestrator.create_task(TaskCreateRequest(message="生成参赛方案", chat_id="oc_demo"))
    orchestrator.confirm_task(created.task_id)
    initial_counts = lark_client.created_artifacts.copy()

    command = TaskMessageService().parse_text(
        "在 Agent-Pilot 参赛方案 中的最后一行添加现在的时间YY-MM-DD HH:MM",
        chat_id="oc_demo",
        message_id="om_revision",
    )
    revised = orchestrator.handle_command(command)

    assert revised is not None
    assert revised.task_id == created.task_id
    assert revised.status == "DONE"
    assert revised.revisions[-1].target_artifacts == ["doc"]
    assert lark_client.created_artifacts == initial_counts
    assert lark_client.updated_artifacts == {"doc": 1, "slides": 0, "canvas": 0}
    assert state_service.get_active_task_id("oc_demo") == created.task_id


def test_doc_revision_inserts_current_time_on_first_line_in_place(tmp_path):
    lark_client = RecordingFakeLarkClient()
    orchestrator = AgentPilotOrchestrator(StateService(tmp_path), lark_client)
    created = orchestrator.create_task(TaskCreateRequest(message="生成参赛方案", chat_id="oc_demo"))
    confirmed = orchestrator.confirm_task(created.task_id)
    initial_doc = _artifact_by_kind(confirmed, "doc")
    initial_counts = lark_client.created_artifacts.copy()

    revised = orchestrator.revise_task(
        created.task_id,
        "修改：在 Agent-Pilot 参赛方案 的文档中的第一行 添加当前日期和时间",
    )

    updated_doc = _artifact_by_kind(revised, "doc")
    doc_content = (tmp_path / "tasks" / created.task_id / "doc.md").read_text(encoding="utf-8")
    assert re.match(r"^\d{4}-\d{2}-\d{2} \d{2}:\d{2}\n# Agent-Pilot", doc_content)
    assert "## 修改记录" not in doc_content
    assert "第一行 添加当前日期和时间" not in doc_content
    assert updated_doc.url == initial_doc.url
    assert updated_doc.token == initial_doc.token
    assert updated_doc.status == "updated"
    assert lark_client.created_artifacts == initial_counts
    assert lark_client.updated_artifacts == {"doc": 1, "slides": 0, "canvas": 0}


def test_slides_revision_updates_existing_deck_without_new_artifact(tmp_path):
    lark_client = RecordingFakeLarkClient()
    orchestrator = AgentPilotOrchestrator(StateService(tmp_path), lark_client)
    created = orchestrator.create_task(TaskCreateRequest(message="生成参赛方案", chat_id="oc_demo"))
    confirmed = orchestrator.confirm_task(created.task_id)
    initial_slides = _artifact_by_kind(confirmed, "slides")
    initial_counts = lark_client.created_artifacts.copy()

    revised = orchestrator.revise_task(created.task_id, "修改：PPT 更突出工程实现")

    updated_slides = _artifact_by_kind(revised, "slides")
    slides = json.loads((tmp_path / "tasks" / created.task_id / "slides.json").read_text(encoding="utf-8"))
    assert any("工程实现" in (slide.get("body") or "") for slide in slides)
    assert updated_slides.url == initial_slides.url
    assert updated_slides.token == initial_slides.token
    assert updated_slides.status == "updated"
    assert lark_client.created_artifacts == initial_counts
    assert lark_client.updated_artifacts == {"doc": 0, "slides": 1, "canvas": 0}


def test_canvas_revision_updates_existing_whiteboard_without_new_artifact(tmp_path):
    lark_client = RecordingFakeLarkClient()
    orchestrator = AgentPilotOrchestrator(StateService(tmp_path), lark_client)
    created = orchestrator.create_task(TaskCreateRequest(message="生成参赛方案", chat_id="oc_demo"))
    confirmed = orchestrator.confirm_task(created.task_id)
    initial_canvas = _artifact_by_kind(confirmed, "canvas")
    initial_counts = lark_client.created_artifacts.copy()

    revised = orchestrator.revise_task(created.task_id, "修改：画板补充工程实现节点")

    updated_canvas = _artifact_by_kind(revised, "canvas")
    mermaid = (tmp_path / "tasks" / created.task_id / "canvas.mmd").read_text(encoding="utf-8")
    assert "工程实现" in mermaid
    assert updated_canvas.url == initial_canvas.url
    assert updated_canvas.token == initial_canvas.token
    assert updated_canvas.status == "updated"
    assert lark_client.created_artifacts == initial_counts
    assert lark_client.updated_artifacts == {"doc": 0, "slides": 0, "canvas": 1}


def test_handle_command_uses_router_targets_instead_of_reparsing(tmp_path):
    lark_client = RecordingFakeLarkClient()
    orchestrator = AgentPilotOrchestrator(StateService(tmp_path), lark_client)
    created = orchestrator.create_task(TaskCreateRequest(message="生成参赛方案", chat_id="oc_demo"))
    orchestrator.confirm_task(created.task_id)
    initial_counts = lark_client.created_artifacts.copy()

    response = orchestrator.handle_command(
        AgentPilotCommand(
            type="revise",
            text="把这个材料改得更适合答辩",
            chat_id="oc_demo",
            target_artifacts=["slides"],
            route_reason="Router Agent resolved material to Slides from chat context.",
        )
    )

    assert response is not None
    assert response.revisions[-1].target_artifacts == ["slides"]
    assert lark_client.created_artifacts == initial_counts
    assert lark_client.updated_artifacts == {"doc": 0, "slides": 1, "canvas": 0}


def test_handle_command_routes_manual_revision_command_when_no_router_metadata(tmp_path):
    lark_client = RecordingFakeLarkClient()
    orchestrator = AgentPilotOrchestrator(StateService(tmp_path), lark_client)
    created = orchestrator.create_task(TaskCreateRequest(message="生成参赛方案", chat_id="oc_demo"))
    orchestrator.confirm_task(created.task_id)

    response = orchestrator.handle_command(
        AgentPilotCommand(
            type="revise",
            text="修改：PPT 更突出工程实现",
            chat_id="oc_demo",
        )
    )

    assert response is not None
    assert response.revisions[-1].target_artifacts == ["slides"]


def test_revision_with_doc_location_hint_targets_only_doc(tmp_path):
    lark_client = RecordingFakeLarkClient()
    orchestrator = AgentPilotOrchestrator(StateService(tmp_path), lark_client)
    created = orchestrator.create_task(TaskCreateRequest(message="生成参赛方案", chat_id="oc_demo"))
    orchestrator.confirm_task(created.task_id)
    initial_counts = lark_client.created_artifacts.copy()

    revised = orchestrator.revise_task(created.task_id, "修改：最后一行添加现在的时间YY-MM-DD HH:MM")

    assert revised.revisions[-1].target_artifacts == ["doc"]
    assert lark_client.created_artifacts == initial_counts
    assert lark_client.updated_artifacts == {"doc": 1, "slides": 0, "canvas": 0}


def test_ambiguous_revision_asks_for_target_instead_of_regenerating_all(tmp_path):
    lark_client = RecordingFakeLarkClient()
    orchestrator = AgentPilotOrchestrator(StateService(tmp_path), lark_client)
    created = orchestrator.create_task(TaskCreateRequest(message="生成参赛方案", chat_id="oc_demo"))
    orchestrator.confirm_task(created.task_id)
    initial_counts = lark_client.created_artifacts.copy()

    revised = orchestrator.revise_task(created.task_id, "修改：更突出工程实现")

    assert revised.status == "DONE"
    assert revised.revisions == []
    assert "请说明要修改哪个产物" in revised.reply
    assert lark_client.created_artifacts == initial_counts


def test_reset_with_active_task_prompts_confirmation(tmp_path):
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
    assert state_service.get_active_task_id("oc_demo") == created.task_id
    assert "确认重置" in lark_client.sent_messages[-1]["text"]


def test_confirm_reset_clears_active_chat_task(tmp_path):
    lark_client = FakeLarkClient()
    state_service = StateService(tmp_path)
    orchestrator = AgentPilotOrchestrator(state_service, lark_client)
    created = orchestrator.create_task(TaskCreateRequest(message="生成参赛方案", chat_id="oc_demo"))

    assert state_service.get_active_task_id("oc_demo") == created.task_id

    response = orchestrator.handle_command(
        AgentPilotCommand(
            type="confirm_reset",
            text="确认重置",
            chat_id="oc_demo",
            message_id="om_demo",
        )
    )

    assert response is None
    assert state_service.get_active_task_id("oc_demo") is None
    assert "已重置" in lark_client.sent_messages[-1]["text"]


def test_reset_without_active_task_shows_no_task_reply(tmp_path):
    lark_client = FakeLarkClient()
    orchestrator = AgentPilotOrchestrator(StateService(tmp_path), lark_client)

    response = orchestrator.handle_command(
        AgentPilotCommand(
            type="reset",
            text="/reset",
            chat_id="oc_demo",
            message_id="om_demo",
        )
    )

    assert response is None
    assert "当前没有活跃任务" in lark_client.sent_messages[-1]["text"]


def test_reset_with_timing_conflict_shows_expired_reply(tmp_path):
    lark_client = FakeLarkClient()
    state_service = StateService(tmp_path)
    orchestrator = AgentPilotOrchestrator(state_service, lark_client)
    created = orchestrator.create_task(TaskCreateRequest(message="生成参赛方案", chat_id="oc_demo"))

    task = state_service.load_task(created.task_id)

    import time as _time
    long_before = _time.time() - 3600

    response = orchestrator.handle_command(
        AgentPilotCommand(
            type="reset",
            text="/reset",
            chat_id="oc_demo",
            message_id="om_demo",
            event_time=long_before,
        )
    )

    assert response is None
    assert state_service.get_active_task_id("oc_demo") == created.task_id
    assert "已过期" in lark_client.sent_messages[-1]["text"]


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
