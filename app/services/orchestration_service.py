from app.schemas.task import TaskCreateRequest, TaskCreateResponse
from app.services.planner_service import build_planning
from app.services.search_service import run_web_research
from app.services.report_service import build_report


'''
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
'''

def run_research(task_id: str, payload: TaskCreateRequest) -> TaskCreateResponse:
    planning = build_planning(payload)

    search_results, source_summary, search_context = run_web_research(
        task_id=task_id,
        payload=payload,
        planning=planning
    )

    local_context_summary = None
    if payload.local_context_path:
        local_context_summary = (
            f"检测到本地资料路径：{payload.local_context_path}。"
            "Day 3 仅保留占位，Day 4 再接真实 RAG。"
        )

    report = build_report(
        payload=payload,
        planning=planning,
        search_results=search_results,
        sources_summary=source_summary,
        search_context=search_context,
        local_context_summary=local_context_summary,
    )
    
    return TaskCreateResponse(
        task_id=task_id,
        status="completed",
        planning=planning,
        research_results=search_results,
        local_context_summary=local_context_summary,
        report=report,
    )