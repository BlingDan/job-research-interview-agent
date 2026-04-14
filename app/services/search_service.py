from app.schemas.task import TaskCreateRequest
from app.schemas.report import PlanningItem, SearchResultItem

def mock_research(
    payload: TaskCreateRequest,
    planning: list[PlanningItem]
) -> list[SearchResultItem]:
    # 这里是一个示例实现，根据实际需求进行修改

    company = payload.company_name or "目标公司"
    topic = payload.interview_topic or "通用面试"

    return [
        SearchResultItem(
            query=planning[0].title,
            title="JD 关键技能抽取",
            snippet="从 JD 中识别到 Python、FastAPI、Agent workflow、结构化输出等关键词。",
            source="mock://jd-analysis",
        ),
        SearchResultItem(
            query=planning[1].title,
            title=f"{company} 背景整理",
            snippet=f"{company} 相关内容先用 mock 文本占位，Day 3 再替换成真实搜索结果。",
            source="mock://company-research",
        ),
        SearchResultItem(
            query=planning[2].title,
            title=f"{topic} 高频问题",
            snippet=f"围绕 {topic} 先生成占位问题、追问方向和准备建议。",
            source="mock://interview-topics",
        ),
    ]