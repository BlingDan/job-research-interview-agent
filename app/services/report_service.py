from app.schemas.report import PlanningItem, SearchResultItem, ReportSection, ReportPayload
from app.schemas.task import TaskCreateRequest, TaskCreateResponse

def build_mock_result(
    payload: TaskCreateRequest,
    planning: list[PlanningItem],
    search_results: list[SearchResultItem],
    local_context_summary: str | None = None,
) -> ReportPayload:
    # 这里是一个示例实现，根据实际需求进行修改
    company = payload.company_name or "目标公司"
    topic = payload.interview_topic or "岗位面试重点"
    
    company_bullets = [search_results[1].snippet]
    if local_context_summary:
        company_bullets.append(local_context_summary)
    
    return ReportPayload(
        title=f"{company} / {topic} 面试准备报告（Mock）",
        summary="已跑通 Day 2 假链路：输入 -> planning -> mock search -> mock report。",

        sections=[
            ReportSection(
                title="岗位要求",
                bullets=[
                    search_results[0].snippet,
                    "今天先验证结构正确，不追求搜索真实性。",
                ],
            ),
            ReportSection(
                title="公司信息",
                bullets=company_bullets,
            ),
            ReportSection(
                title="面试高频点",
                bullets=[search_results[2].snippet],
            ),
            ReportSection(
                title="下一步开发",
                bullets=[
                    "Day 3 接真实搜索",
                    "Day 4 接本地资料解析 / 切块 / 检索",
                ],
            ),
        ],
        next_actions=[
            "把 mock search 替换成真实搜索实现",
            "增加来源列表与引用展示",
            "后续再把 stream 事件绑定 task_id",
        ],
    )