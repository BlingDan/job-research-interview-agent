import json
from textwrap import dedent

from app.core.llm import JobResearchLLM
from app.schemas.memory import CandidateProfile
from app.schemas.state import TaskSummary, TodoItem

REPORT_SYSTEM_PROMPT = dedent(
    """
    你是一个求职面试准备 Report Writer Agent。
    你的任务是基于规划结果、任务级研究笔记、本地资料和候选人记忆，
    生成结构化面试准备报告。

    输出要求：
    1. 只返回 JSON 对象
    2. 不要返回 Markdown 代码块
    3. 优先基于事实，不要臆造
    4. 公开搜索结果只能作为岗位、公司、面试背景，不能直接作为候选人能力证据
    5. 候选人能力必须来自候选人长期画像、本地资料、用户备注或项目级记忆
    6. 输出字段必须包含：
       - title
       - summary
       - sections
       - next_actions
       - references
    7. sections 中每一项必须包含：
       - title
       - bullets
       - sources
    """
).strip()

def generate_report_text(
    planning: list[TodoItem],
    task_summaries: list[TaskSummary],
    *,
    local_context_summary: str | None = None,
    candidate_profile: CandidateProfile | None = None,
    project_memory: str | None = None,
    consolidated_memory: str | None = None,
) -> str:
    llm = JobResearchLLM(
        temperature=0.2,
        max_tokens=2400,
    )

    planning_payload = [
        {
            "id": item.id,
            "title": item.title,
            "intent": item.intent,
            "query": item.query,
            "category": item.category,
        }
        for item in planning
    ]

    summary_payload = [
        {
            "todo_id": item.todo_id,
            "title": item.title,
            "category": item.category,
            "question_answered": item.question_answered,
            "key_points": item.key_points,
            "open_questions": item.open_questions,
            "sources": item.sources,
        }
        for item in task_summaries
    ]
    candidate_profile_payload = (
        candidate_profile.model_dump(mode="json")
        if candidate_profile is not None
        else None
    )

    user_prompt = dedent(
        f"""
        研究规划：
        {json.dumps(planning_payload, ensure_ascii=False, indent=2)}

        任务级研究笔记：
        {json.dumps(summary_payload, ensure_ascii=False, indent=2)}

        候选人本地资料摘要：
        {local_context_summary or "未提供"}

        候选人长期画像：
        {json.dumps(candidate_profile_payload, ensure_ascii=False, indent=2) if candidate_profile_payload else "未提供"}

        项目级记忆：
        {project_memory or "未提供"}

        压缩记忆：
        {consolidated_memory or "未提供"}

        请输出一份结构化面试准备报告，报告结构建议覆盖：
        1. 岗位要求拆解
        2. 公司/业务/团队信息
        3. 高频技术面试点
        4. 你的项目/经历匹配点
        5. 你的差距与补齐建议
        6. 建议准备的追问清单
        7. 参考来源

        在“项目/经历匹配点”和“差距建议”里，优先结合候选人长期画像、
        项目级记忆、压缩记忆和本地资料；不要把公开搜索结果误写成候选人本人能力。
        """
    ).strip()

    messages = [
        {"role": "system", "content": REPORT_SYSTEM_PROMPT},
        {"role": "user", "content": user_prompt},
    ]
    return llm.invoke(messages).strip()
