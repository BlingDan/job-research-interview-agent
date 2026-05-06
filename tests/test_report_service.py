from __future__ import annotations

from app.schemas.memory import CandidateProfile, SkillMemory
from app.schemas.report import ReportPayload, ReportSection
from app.schemas.state import ResearchState, TaskSummary, TodoItem
from app.schemas.task import TaskCreateRequest
from app.services.report_service import build_report, render_report_markdown


def _make_state() -> ResearchState:
    return ResearchState(
        task_id="demo-task",
        input=TaskCreateRequest(jd_text="需要 Python FastAPI Agent 能力"),
        planning=[
            TodoItem(
                id="todo-1",
                title="岗位核心能力拆解",
                intent="提取岗位关键技能",
                query="Python FastAPI Agent workflow requirements",
                category="jd",
            )
        ],
        task_summaries=[
            TaskSummary(
                todo_id="todo-1",
                title="岗位核心能力拆解",
                category="jd",
                question_answered="该任务回答了岗位要求。",
                key_points=["需要 Python", "需要 FastAPI"],
                open_questions=[],
                needs_followup=False,
                followup_queries=[],
                sources=["https://example.com/jd"],
                summary_markdown="## 任务：岗位核心能力拆解",
            )
        ],
    )


def test_build_report_from_agent_json(monkeypatch) -> None:
    from app.services import report_service
    captured = {}

    raw_text = """
    {
      "title": "面试准备研究报告",
      "summary": "已完成岗位、公司和面试主题的结构化研究。",
      "sections": [
        {
          "title": "岗位要求拆解",
          "bullets": ["需要 Python", "需要 FastAPI"],
          "sources": ["https://example.com/jd"]
        },
        {
          "title": "你的差距与补齐建议",
          "bullets": ["补充 Agent 工作流表达", "补充 SSE 实战案例"],
          "sources": []
        }
      ],
      "next_actions": ["整理项目亮点", "补齐面试追问清单"],
      "references": ["https://example.com/jd"]
    }
    """

    def _generate_report_text(**kwargs):
        captured.update(kwargs)
        return raw_text

    monkeypatch.setattr(report_service, "generate_report_text", _generate_report_text)

    state = _make_state()
    state.candidate_profile = CandidateProfile(
        skills=[SkillMemory(name="FastAPI", level="project", evidence=["本地资料"], confidence=0.9)]
    )
    state.project_memory = "# Project Memory\n\n- 项目级记忆"
    state.consolidated_memory = "# Consolidated Memory\n\n- FastAPI"

    report = build_report(state)

    assert report.title == "面试准备研究报告"
    assert len(report.sections) == 2
    assert report.sections[0].title == "岗位要求拆解"
    assert report.references == ["https://example.com/jd"]
    assert captured["candidate_profile"].skills[0].name == "FastAPI"
    assert captured["project_memory"] == "# Project Memory\n\n- 项目级记忆"
    assert captured["consolidated_memory"] == "# Consolidated Memory\n\n- FastAPI"


def test_build_report_falls_back_when_agent_output_invalid(monkeypatch) -> None:
    from app.services import report_service

    monkeypatch.setattr(
        report_service,
        "generate_report_text",
        lambda **kwargs: "not-json",
    )

    state = _make_state()
    state.candidate_profile = CandidateProfile(
        skills=[SkillMemory(name="FastAPI", level="project", evidence=["本地资料"], confidence=0.9)],
        target_roles=["AI 应用后端"],
    )
    state.consolidated_memory = "# Consolidated Memory\n\n- 当前弱项：SSE 真实任务流"

    report = build_report(state)

    assert report.title == "面试准备研究报告"
    assert report.sections[0].title == "岗位核心能力拆解"
    assert "https://example.com/jd" in report.references
    assert any(section.title == "候选人长期画像与项目匹配" for section in report.sections)
    matching_section = next(section for section in report.sections if section.title == "候选人长期画像与项目匹配")
    assert any("FastAPI" in bullet for bullet in matching_section.bullets)
    assert any("AI 应用后端" in bullet for bullet in matching_section.bullets)


def test_render_report_markdown_renders_sections_and_references() -> None:
    report = ReportPayload(
        title="面试准备研究报告",
        summary="已完成研究。",
        sections=[
            ReportSection(
                title="岗位要求拆解",
                bullets=["需要 Python", "需要 FastAPI"],
                sources=["https://example.com/jd"],
            )
        ],
        next_actions=["整理项目亮点"],
        references=["https://example.com/jd"],
    )

    markdown = render_report_markdown(report)

    assert "# 面试准备研究报告" in markdown
    assert "## 岗位要求拆解" in markdown
    assert "- 需要 Python" in markdown
    assert "## 参考来源" in markdown
