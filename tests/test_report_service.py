from __future__ import annotations

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

    monkeypatch.setattr(
        report_service,
        "generate_report_text",
        lambda planning, task_summaries, local_context_summary=None: raw_text,
    )

    report = build_report(_make_state())

    assert report.title == "面试准备研究报告"
    assert len(report.sections) == 2
    assert report.sections[0].title == "岗位要求拆解"
    assert report.references == ["https://example.com/jd"]


def test_build_report_falls_back_when_agent_output_invalid(monkeypatch) -> None:
    from app.services import report_service

    monkeypatch.setattr(
        report_service,
        "generate_report_text",
        lambda planning, task_summaries, local_context_summary=None: "not-json",
    )

    report = build_report(_make_state())

    assert report.title == "面试准备研究报告"
    assert report.sections[0].title == "岗位核心能力拆解"
    assert "https://example.com/jd" in report.references


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
