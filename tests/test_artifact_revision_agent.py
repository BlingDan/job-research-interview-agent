from datetime import datetime

from app.agents.artifact_revision_agent import (
    apply_canvas_patch,
    apply_doc_patch,
    apply_slides_patch,
    build_artifact_revision_patch,
)


def test_doc_patch_resolves_current_time_and_inserts_first_line():
    patch = build_artifact_revision_patch(
        "修改：在 Agent-Pilot 参赛方案 的文档中的第一行 添加当前日期和时间",
        "doc",
        now=lambda: datetime(2026, 4, 28, 16, 57),
    )

    result = apply_doc_patch("# Agent-Pilot\n正文", patch)

    assert patch.operation == "insert"
    assert patch.location == "first_line"
    assert patch.content == "2026-04-28 16:57"
    assert result == "2026-04-28 16:57\n# Agent-Pilot\n正文"


def test_doc_patch_requires_clarification_for_unknown_section():
    patch = build_artifact_revision_patch("修改：把不存在的章节写得更好", "doc")

    assert patch.needs_clarification is True
    assert "章节" in patch.clarification_question


def test_slide_patch_updates_requested_page_only():
    patch = build_artifact_revision_patch("修改：第2页增加工程实现路径", "slides")
    slides = [
        {"title": "封面", "body": "价值"},
        {"title": "架构", "body": "Agent 编排"},
    ]

    updated = apply_slides_patch(slides, patch)

    assert "工程实现路径" not in updated[0]["body"]
    assert "工程实现路径" in updated[1]["body"]


def test_canvas_patch_appends_mermaid_node():
    patch = build_artifact_revision_patch("修改：画板补充工程实现节点", "canvas")

    updated = apply_canvas_patch("flowchart LR\n    A --> B\n", patch)

    assert "工程实现节点" in updated
    assert "RevisionNote" in updated
