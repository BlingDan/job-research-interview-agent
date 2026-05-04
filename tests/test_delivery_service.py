from app.agents.planner_agent import build_fallback_plan
from app.schemas.agent_pilot import AgentPilotTask, ArtifactRef, RevisionRecord
from app.services.delivery_service import (
    FALLBACK_NOTICE,
    format_final_reply,
    format_help_reply,
    format_plan_reply_chunks,
    format_plan_reply,
    format_progress_reply,
    format_reset_confirm_reply,
    format_reset_expired_reply,
    format_revision_reply,
    with_fallback_notice,
)


def test_plan_reply_includes_confirmation():
    task = AgentPilotTask(task_id="task-1", input_text="生成方案", plan=build_fallback_plan("生成方案"))

    reply = format_plan_reply(task)

    assert "确认" in reply
    assert "生成项目方案文档" in reply


def test_plan_reply_chunks_are_cumulative():
    task = AgentPilotTask(task_id="task-1", input_text="生成方案", plan=build_fallback_plan("生成方案"))

    chunks = format_plan_reply_chunks(task)

    assert chunks[0] == "已理解需求，正在拆解执行计划..."
    assert "1. 意图捕捉与任务规划" in chunks[1]
    assert chunks[-1] == format_plan_reply(task)


def test_progress_reply_includes_status_and_next_action():
    task = AgentPilotTask(task_id="task-1", input_text="生成方案", status="WAITING_CONFIRMATION")

    reply = format_progress_reply(task)

    assert "WAITING_CONFIRMATION" in reply
    assert "等待你回复" in reply


def test_final_reply_includes_artifact_links():
    task = AgentPilotTask(
        task_id="task-1",
        input_text="生成方案",
        artifacts=[
            ArtifactRef(
                artifact_id="a1",
                kind="doc",
                title="方案",
                url="https://fake/doc",
                status="fake",
            )
        ],
    )

    reply = format_final_reply(task)

    assert "https://fake/doc" in reply


def test_revision_reply_mentions_targets():
    task = AgentPilotTask(task_id="task-1", input_text="生成方案", status="DONE")
    revision = RevisionRecord(
        revision_id="r1",
        instruction="修改：PPT 更突出工程实现",
        target_artifacts=["slides"],
    )

    reply = format_revision_reply(task, revision)

    assert "slides" in reply
    assert "PPT" in reply


def test_help_reply_mentions_natural_revision_language():
    reply = format_help_reply()

    assert "不加「修改：」" in reply


def test_reset_confirm_reply_includes_plan_summary_and_confirm_reset():
    task = AgentPilotTask(
        task_id="task-1",
        input_text="生成方案",
        plan=build_fallback_plan("生成方案"),
        status="WAITING_CONFIRMATION",
    )

    reply = format_reset_confirm_reply(task)

    assert "确认重置" in reply
    assert "WAITING_CONFIRMATION" in reply


def test_reset_expired_reply_mentions_expired():
    reply = format_reset_expired_reply()

    assert "已过期" in reply


def test_with_fallback_notice_prepends_warning():
    reply = with_fallback_notice("任务已完成，成果如下：", "fallback")

    assert reply.startswith(FALLBACK_NOTICE)
    assert "任务已完成" in reply


def test_with_fallback_notice_passes_through_for_llm():
    reply = with_fallback_notice("任务已完成，成果如下：", "llm")

    assert FALLBACK_NOTICE not in reply
    assert reply == "任务已完成，成果如下："


def test_with_fallback_notice_passes_through_for_hard_command():
    reply = with_fallback_notice("在线", "hard_command")

    assert FALLBACK_NOTICE not in reply


def test_with_fallback_notice_passes_through_for_none():
    reply = with_fallback_notice("在线", None)

    assert FALLBACK_NOTICE not in reply
