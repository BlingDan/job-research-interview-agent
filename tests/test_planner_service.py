from __future__ import annotations

from app.schemas.task import TaskCreateRequest
from app.services.planner_service import build_planning, parse_planner_output


def test_parse_planner_output_extracts_fenced_json_array() -> None:
    raw_text = """
    先给出规划结果：

    ```json
    [
      {
        "title": "岗位核心能力拆解",
        "intent": "提取岗位关键技能",
        "query": "Python FastAPI Agent workflow requirements",
        "category": "jd"
      },
      {
        "title": "公司业务背景调研",
        "intent": "梳理公司业务和技术栈",
        "query": "OpenAI 公司 业务 技术栈 团队",
        "category": "company"
      },
      {
        "title": "高频技术面试点整理",
        "intent": "整理常见面试题",
        "query": "FastAPI Agent 高频面试题",
        "category": "interview"
      }
    ]
    ```
    """

    parsed = parse_planner_output(raw_text)

    assert len(parsed) == 3
    assert parsed[0]["category"] == "jd"
    assert parsed[1]["title"] == "公司业务背景调研"


def test_build_planning_parses_valid_json(monkeypatch) -> None:
    from app.services import planner_service

    raw_text = """
    [
      {
        "title": "岗位核心能力拆解",
        "intent": "提取岗位关键技能",
        "query": "Python FastAPI Agent workflow requirements",
        "category": "jd"
      },
      {
        "title": "公司业务背景调研",
        "intent": "梳理公司业务和技术栈",
        "query": "OpenAI 公司 业务 技术栈 团队",
        "category": "company"
      },
      {
        "title": "高频技术面试点整理",
        "intent": "整理常见面试题",
        "query": "FastAPI Agent 高频面试题",
        "category": "interview"
      }
    ]
    """

    monkeypatch.setattr(planner_service, "generate_planning_text", lambda payload: raw_text)

    payload = TaskCreateRequest(jd_text="需要 Python FastAPI Agent 能力")
    planning = build_planning(payload)

    assert len(planning) == 3
    assert planning[0].id == "todo-1"
    assert planning[0].category == "jd"
    assert planning[1].category == "company"


def test_build_planning_falls_back_when_agent_output_invalid(monkeypatch) -> None:
    from app.services import planner_service

    monkeypatch.setattr(planner_service, "generate_planning_text", lambda payload: "not-json")

    payload = TaskCreateRequest(
        jd_text="需要 Python FastAPI Agent 能力",
        company_name="OpenAI",
        interview_topic="Agent backend",
    )
    planning = build_planning(payload)

    assert 3 <= len(planning) <= 5
    assert {item.category for item in planning} == {
        "jd",
        "company",
        "interview",
        "candidate_gap",
    }
