from app.schemas.task import TaskCreateRequest, TaskCreateResponse
from app.schemas.report import PlanningItem
from app.services.research_coordinator import ResearchCoordinator



def run_research(task_id: str, payload: TaskCreateRequest) -> TaskCreateResponse:
    coordinator = ResearchCoordinator(task_id=task_id, payload=payload)
    state = coordinator.run()

    planning = [
        PlanningItem(
            step=index,
            title=item.title,
            objective=item.intent,
        )
        for index, item in enumerate(state.planning, start=1)
    ]

    if state.report is None:
        raise ValueError("report was not generated")
    return TaskCreateResponse(
        task_id=task_id,
        status=state.status,
        planning=planning,
        research_results=state.search_results,
        local_context_summary=state.local_context,
        report=state.report,
    )