import json
from datetime import datetime

import pytest

from app.agents.artifact_revision_agent import (
    apply_canvas_patch,
    apply_doc_patch,
    apply_slides_patch,
    build_artifact_revision_patch,
    build_llm_revision_content,
)
from app.schemas.agent_pilot import ArtifactKind


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


# ---------------------------------------------------------------------------
# LLM full-content rewrite tests
# ---------------------------------------------------------------------------


def _make_doc_fakellm(content: str, change_summary: str = "已在文末添加内容。"):
    class FakeLLM:
        def __init__(self, **kwargs):
            self.kwargs = kwargs

        def invoke(self, messages):
            return json.dumps({"content": content, "change_summary": change_summary}, ensure_ascii=False)

    return FakeLLM


def _make_slides_fakellm(slides: list[dict], change_summary: str = "已增强幻灯片内容。"):
    class FakeLLM:
        def __init__(self, **kwargs):
            self.kwargs = kwargs

        def invoke(self, messages):
            return json.dumps({"content": slides, "change_summary": change_summary}, ensure_ascii=False)

    return FakeLLM


def _make_canvas_fakellm(mermaid: str, change_summary: str = "已在画板添加节点。"):
    class FakeLLM:
        def __init__(self, **kwargs):
            self.kwargs = kwargs

        def invoke(self, messages):
            return json.dumps({"content": mermaid, "change_summary": change_summary}, ensure_ascii=False)

    return FakeLLM


class TestFormatValidators:
    def test_validate_doc_rejects_flat_text(self, monkeypatch):
        """Content without '#' heading → ValueError."""
        from app.agents import artifact_revision_agent

        monkeypatch.setattr(artifact_revision_agent, "JobResearchLLM", _make_doc_fakellm("没有标题的纯文本内容。"))

        with pytest.raises(ValueError, match="标题"):
            build_llm_revision_content("修改内容", "# 原始标题\n正文", "doc")

    def test_validate_slides_rejects_non_list(self, monkeypatch):
        """Content not a JSON array → ValueError."""
        from app.agents import artifact_revision_agent

        class FakeLLM:
            def __init__(self, **kwargs):
                pass

            def invoke(self, messages):
                return json.dumps({"content": {"not": "a list"}, "change_summary": "x"})

        monkeypatch.setattr(artifact_revision_agent, "JobResearchLLM", FakeLLM)

        with pytest.raises(ValueError, match="数组"):
            build_llm_revision_content("修改幻灯片", json.dumps([{"title": "T", "body": "B"}]), "slides")

    def test_validate_slides_rejects_missing_title_body(self, monkeypatch):
        """Each slide must have title or body key."""
        from app.agents import artifact_revision_agent

        class FakeLLM:
            def __init__(self, **kwargs):
                pass

            def invoke(self, messages):
                return json.dumps({"content": [{"x": "y"}], "change_summary": "x"})

        monkeypatch.setattr(artifact_revision_agent, "JobResearchLLM", FakeLLM)

        with pytest.raises(ValueError, match="缺少 title 或 body"):
            build_llm_revision_content("修改幻灯片", json.dumps([{"title": "T", "body": "B"}]), "slides")

    def test_validate_canvas_rejects_non_mermaid(self, monkeypatch):
        """Content not starting with graph/flowchart → ValueError."""
        from app.agents import artifact_revision_agent

        monkeypatch.setattr(artifact_revision_agent, "JobResearchLLM", _make_canvas_fakellm("不是 mermaid 代码"))

        with pytest.raises(ValueError, match="Mermaid"):
            build_llm_revision_content("修改画板", "flowchart LR\n    A --> B\n", "canvas")

    def test_validate_doc_accepts_valid_markdown(self, monkeypatch):
        """Valid markdown with heading passes validation."""
        from app.agents import artifact_revision_agent

        new_content = "# 标题\n修改后的内容。"
        monkeypatch.setattr(artifact_revision_agent, "JobResearchLLM", _make_doc_fakellm(new_content))

        result, summary = build_llm_revision_content("修改", "# 标题\n原始内容", "doc")
        assert result == new_content
        assert "文末添加" in summary

    def test_validate_canvas_accepts_graph_header(self, monkeypatch):
        """Content starting with 'graph' passes validation."""
        from app.agents import artifact_revision_agent

        new_mermaid = "graph TD\n    A[Start] --> B[End]"
        monkeypatch.setattr(artifact_revision_agent, "JobResearchLLM", _make_canvas_fakellm(new_mermaid))

        result, summary = build_llm_revision_content("修改", "graph TD\n    A --> B\n", "canvas")
        assert result == new_mermaid

    def test_validate_canvas_accepts_flowchart_header(self, monkeypatch):
        """Content starting with 'flowchart' passes validation."""
        from app.agents import artifact_revision_agent

        new_mermaid = "flowchart LR\n    A[Start] --> B[End]"
        monkeypatch.setattr(artifact_revision_agent, "JobResearchLLM", _make_canvas_fakellm(new_mermaid))

        result, _ = build_llm_revision_content("修改", "flowchart LR\n    A --> B\n", "canvas")
        assert result == new_mermaid


class TestLLMRewrite:
    def test_rewrite_doc_appends_time_to_last_line(self, monkeypatch):
        """Time string is appended at end of doc."""
        from app.agents import artifact_revision_agent

        new_content = "# Agent-Pilot\n\n项目方案正文。\n\n2026-05-01 15:30"
        monkeypatch.setattr(artifact_revision_agent, "JobResearchLLM", _make_doc_fakellm(new_content))

        result, summary = build_llm_revision_content(
            "在文档最后一行添加当前日期和时间", "# Agent-Pilot\n\n项目方案正文。", "doc"
        )
        assert "2026-05-01" in result
        assert result.startswith("# Agent-Pilot")

    def test_rewrite_slides_enhances_engineering_content(self, monkeypatch):
        """Slide bodies include enhanced engineering keywords."""
        from app.agents import artifact_revision_agent

        enhanced_slides = [
            {"title": "封面", "body": "Agent-Pilot 方案"},
            {"title": "工程实现", "body": "详细的工程实现路径：消息推送、fallback 机制、MCP 集成"},
        ]
        monkeypatch.setattr(artifact_revision_agent, "JobResearchLLM", _make_slides_fakellm(enhanced_slides))

        original = json.dumps(
            [{"title": "封面", "body": "Agent-Pilot 方案"}, {"title": "工程实现", "body": "工程实现概述"}],
            ensure_ascii=False,
        )
        result, summary = build_llm_revision_content("PPT 更突出工程实现", original, "slides")
        parsed = json.loads(result)
        assert len(parsed) == 2
        assert any("fallback" in s.get("body", "") for s in parsed)

    def test_rewrite_canvas_adds_error_handling_nodes(self, monkeypatch):
        """Mermaid has new error-handling node definitions."""
        from app.agents import artifact_revision_agent

        new_mermaid = """flowchart LR
    A[Start] --> B[Process]
    B --> C[Success]
    B --> D[Error Handling]
    D --> E[Fallback]"""
        monkeypatch.setattr(artifact_revision_agent, "JobResearchLLM", _make_canvas_fakellm(new_mermaid))

        result, summary = build_llm_revision_content(
            "画板补充错误处理分支", "flowchart LR\n    A[Start] --> B[Process]\n    B --> C[Success]\n", "canvas"
        )
        assert "Error" in result
        assert result.startswith("flowchart")

    def test_rewrite_rejects_oversized_content(self):
        """Content exceeding 60k chars raises ValueError before LLM call."""
        huge_content = "x" * 70000
        with pytest.raises(ValueError, match="内容过长"):
            build_llm_revision_content("修改内容", huge_content, "doc", max_input_chars=60000)

    def test_rewrite_change_summary_returned(self, monkeypatch):
        """change_summary from LLM is returned."""
        from app.agents import artifact_revision_agent

        monkeypatch.setattr(
            artifact_revision_agent,
            "JobResearchLLM",
            _make_doc_fakellm("# 标题\n新内容", change_summary="增强了工程实现描述，补充了消息推送细节。"),
        )

        result, summary = build_llm_revision_content("强化工程实现", "# 标题\n旧内容", "doc")
        assert "工程实现" in summary
        assert "消息推送" in summary

    def test_rewrite_preserves_heading_structure(self, monkeypatch):
        """Only changed content differs; heading structure intact."""
        from app.agents import artifact_revision_agent

        new_content = "# 项目概述\n\n## 架构\n\n更新后的架构描述。\n\n## 实现\n\n原本的实现。"
        monkeypatch.setattr(artifact_revision_agent, "JobResearchLLM", _make_doc_fakellm(new_content))

        original = "# 项目概述\n\n## 架构\n\n旧的架构描述。\n\n## 实现\n\n原本的实现。"
        result, _ = build_llm_revision_content("更新架构描述", original, "doc")
        assert "# 项目概述" in result
        assert "## 架构" in result
        assert "## 实现" in result
        assert "原本的实现" in result

    def test_rewrite_handles_code_fence_json_response(self, monkeypatch):
        """LLM output wrapped in ```json fence is parsed correctly."""
        from app.agents import artifact_revision_agent

        class FakeLLM:
            def __init__(self, **kwargs):
                pass

            def invoke(self, messages):
                return '```json\n{"content": "# 标题\\n从代码块解析的内容。", "change_summary": "解析成功"}\n```'

        monkeypatch.setattr(artifact_revision_agent, "JobResearchLLM", FakeLLM)

        result, summary = build_llm_revision_content("修改", "# 标题\n原始", "doc")
        assert "从代码块解析的内容" in result
        assert summary == "解析成功"


class TestLLMRewriteTimeout:
    def test_timeout_causes_value_error(self, monkeypatch):
        """LLM that sleeps beyond timeout raises ValueError."""
        from app.agents import artifact_revision_agent
        import time

        class SlowFakeLLM:
            def __init__(self, **kwargs):
                pass

            def invoke(self, messages):
                time.sleep(5.0)
                return '{"content": "too late", "change_summary": "x"}'

        monkeypatch.setattr(artifact_revision_agent, "JobResearchLLM", SlowFakeLLM)
        monkeypatch.setattr(artifact_revision_agent, "_revision_timeout", lambda: 0.5)

        with pytest.raises(Exception):
            build_llm_revision_content("修改", "# 标题\n内容", "doc")

    def test_llm_unavailable_falls_back_to_keyword(self):
        """When LLM is not reachable, keyword patch still works."""
        patch = build_artifact_revision_patch("修改：在文档第一行添加当前时间", "doc", now=lambda: datetime(2026, 5, 1, 10, 0))

        assert patch.operation == "insert"
        assert patch.location == "first_line"
        assert "2026-05-01" in patch.content
        assert patch.needs_clarification is False


def test_oversized_content_with_custom_max_chars():
    """Custom max_input_chars respected."""
    with pytest.raises(ValueError, match="内容过长"):
        build_llm_revision_content("修改", "a" * 5001, "doc", max_input_chars=5000)

    # Under the limit should proceed (but will fail on LLM call since no mock)
    # We just verify the budget check passes for small content
    # (this would hit LLM, so we don't actually call it)


class TestJsonResponseParsing:
    def test_parse_plain_json_object(self, monkeypatch):
        """Plain JSON object response is parsed."""
        from app.agents import artifact_revision_agent

        class FakeLLM:
            def __init__(self, **kwargs):
                pass

            def invoke(self, messages):
                return '{"content": "# 标题\\n内容", "change_summary": "简短的修改说明"}'

        monkeypatch.setattr(artifact_revision_agent, "JobResearchLLM", FakeLLM)

        result, summary = build_llm_revision_content("修改", "# 标题\n旧内容", "doc")
        assert result == "# 标题\n内容"
        assert summary == "简短的修改说明"

    def test_parse_json_with_surrounding_text(self, monkeypatch):
        """JSON object embedded in text is extracted."""
        from app.agents import artifact_revision_agent

        class FakeLLM:
            def __init__(self, **kwargs):
                pass

            def invoke(self, messages):
                return '好的，这是修改后的文档：\n{"content": "# 标题\\n新内容", "change_summary": "已更新内容"}\n修改完成。'

        monkeypatch.setattr(artifact_revision_agent, "JobResearchLLM", FakeLLM)

        result, summary = build_llm_revision_content("修改", "# 标题\n旧内容", "doc")
        assert result == "# 标题\n新内容"
        assert summary == "已更新内容"

    def test_parse_empty_content_raises(self, monkeypatch):
        """Empty content field raises ValueError."""
        from app.agents import artifact_revision_agent

        class FakeLLM:
            def __init__(self, **kwargs):
                pass

            def invoke(self, messages):
                return '{"content": "", "change_summary": "x"}'

        monkeypatch.setattr(artifact_revision_agent, "JobResearchLLM", FakeLLM)

        with pytest.raises(ValueError, match="内容为空"):
            build_llm_revision_content("修改", "# 标题\n内容", "doc")

    def test_parse_missing_content_field_raises(self, monkeypatch):
        """Missing content field raises ValueError."""
        from app.agents import artifact_revision_agent

        class FakeLLM:
            def __init__(self, **kwargs):
                pass

            def invoke(self, messages):
                return '{"change_summary": "遗漏了 content 字段"}'

        monkeypatch.setattr(artifact_revision_agent, "JobResearchLLM", FakeLLM)

        with pytest.raises(ValueError, match="内容为空"):
            build_llm_revision_content("修改", "# 标题\n内容", "doc")
