from app.schemas.task import TaskCreateRequest
from app.schemas.report import PlanningItem

def build_planning(payload: TaskCreateRequest) -> list[PlanningItem]:
    # 这里是一个示例实现，根据实际需求进行修改

    company = payload.company_name or "目标公司"
    topic = payload.interview_topic or "岗位面试重点"
    planning = [
        PlanningItem(
            step=1, 
            title="理解职位描述", 
            objective="分析JD文本，提取关键信息"
            ),
        PlanningItem(
            step=2, 
            title="公司背景调查", 
            objective=f"整理{company}的业务、团队和技术环境"),
        PlanningItem(
            step=3, 
            title="面试话题准备", 
            objective=f"针对{topic}准备相关问题和答案"),
        PlanningItem(
            step=4, 
            title="形成建议", 
            objective="输出差距分析与下一步准备动作"),
    ]
    return planning