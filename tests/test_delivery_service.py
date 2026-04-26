from app.agents.planner_agent import build_fallback_plan
from app.schemas.agent_pilot import AgentPilotTask, ArtifactRef, RevisionRecord
from app.services.delivery_service import (
    format_final_reply,
    format_plan_reply,
    format_progress_reply,
    format_revision_reply,
)


def test_plan_reply_includes_confirmation():
    task = AgentPilotTask(task_id="task-1", input_text="生成方案", plan=build_fallback_plan("生成方案"))

    reply = format_plan_reply(task)

    assert "确认" in reply
    assert "生成参赛方案文档" in reply


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

