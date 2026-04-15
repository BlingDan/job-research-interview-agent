from app.schemas.report import PlanningItem, SearchResultItem, ReportSection, ReportPayload
from app.schemas.task import TaskCreateRequest, TaskCreateResponse
from collections import defaultdict


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


def build_report(
    payload: TaskCreateRequest,
    planning: list[PlanningItem],
    search_results: list[SearchResultItem],
    sources_summary: str,
    search_context: str,
    local_context_summary: str | None = None,
) -> ReportPayload:
    company = payload.company_name or "目标公司"
    topic = payload.interview_topic or "岗位面试重点"

    grouped: dict[str, list[SearchResultItem]] = defaultdict(list)
    for item in search_results:
        grouped[item.category or "other"].append(item)

    valid_sources = {
        item.source
        for item in search_results
        if not item.source.startswith(("error://", "empty://", "config://"))
    }

    company_bullets = _results_to_bullets(grouped.get("company", []), limit=2)
    if local_context_summary:
        company_bullets.append(local_context_summary)

    return ReportPayload(
        title=f"{company} / {topic} 面试准备报告",
        summary=(
            f"已完成 Day 3 真实搜索链路：planning -> Tavily search -> "
            f"normalize -> context -> report。当前汇总 {len(valid_sources)} 个有效来源。"
        ),
        sections=[
            ReportSection(
                title="岗位要求",
                bullets=_results_to_bullets(grouped.get("jd", []), limit=2),
            ),
            ReportSection(
                title="公司信息",
                bullets=company_bullets,
            ),
            ReportSection(
                title="面试高频点",
                bullets=_results_to_bullets(grouped.get("interview", []), limit=2),
            ),
            ReportSection(
                title="来源概览",
                bullets=sources_summary.splitlines()[:5] or ["暂无有效来源"],
            ),
            ReportSection(
                title="下一步开发",
                bullets=[
                    "Day 4 接本地资料解析、切块与检索。",
                    "把 search_context 接到后续总结链路。",
                    "后续再考虑 query 优化、rerank 和缓存。",
                ],
            ),
        ],
        next_actions=[
            "检查 workspace 中保存的 raw_search.json 和 search_results.json。",
            "观察哪些 query 结果过泛，再迭代 query 模板。",
            "后续把 stream 事件绑定到真实 task_id。",
        ],
    )
    

def _results_to_bullets(result: list[SearchResultItem], limit: int = 2) -> list[str]:
    bullets: list[str] = []
    
    for item in result[:limit]:
        bullets.append(f"{item.title}：{item.snippet}（来源：{item.source}）")
    if not bullets:
        bullets.append("暂无有效搜索结果。先检查 query 设计、API key 和网络配置。")

    return bullets