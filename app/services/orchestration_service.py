from threading import local
from app.schemas.task import TaskCreateRequest, TaskCreateResponse
from app.services.planner_service import build_planning
from app.services.search_service import mock_research
from app.services.report_service import build_mock_result


def run_mock_research(task_id:str, payload: TaskCreateRequest) -> TaskCreateResponse:

    # 1. 生成规划
    planning = build_planning(payload)
    # 2. 执行 mock 研究
    search_results = mock_research(payload, planning)
    
    # 本地资料解析
    local_context_summary = None 
    if payload.local_context_path:
        local_context_summary = (
            f"检测到本地资料路径：{payload.local_context_path}。"
            "Day 2 仅保留占位，Day 4 再接真实 RAG。"
        )
    
    # 生成 report
    report = build_mock_result(
        payload=payload, 
        planning=planning, 
        search_results=search_results, 
        local_context_summary=local_context_summary
        )

    return TaskCreateResponse(
        task_id=task_id,
        status="completed_mock",
        planning=planning,
        research_results=search_results,
        local_context_summary=local_context_summary,
        report=report,
    )
