import json
from textwrap import dedent

from app.core.llm import JobResearchLLM
from app.schemas.state import TaskSummary, TodoItem

REPORT_SYSTEM_PROMPT = dedent(
    """
    你是一个求职面试准备 Report Writer Agent。
    你的任务是基于规划结果和任务级研究笔记，生成结构化面试准备报告。

    输出要求：
    1. 只返回 JSON 对象
    2. 不要返回 Markdown 代码块
    3. 优先基于事实，不要臆造
    4. 输出字段必须包含：
       - title
       - summary
       - sections
       - next_actions
       - references
    5. sections 中每一项必须包含：
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

    user_prompt = dedent(
        f"""
        研究规划：
        {json.dumps(planning_payload, ensure_ascii=False, indent=2)}

        任务级研究笔记：
        {json.dumps(summary_payload, ensure_ascii=False, indent=2)}

        候选人本地资料摘要：
        {local_context_summary or "未提供"}

        请输出一份结构化面试准备报告，报告结构建议覆盖：
        1. 岗位要求拆解
        2. 公司/业务/团队信息
        3. 高频技术面试点
        4. 你的项目/经历匹配点
        5. 你的差距与补齐建议
        6. 建议准备的追问清单
        7. 参考来源
        """
    ).strip()

    messages = [
        {"role": "system", "content": REPORT_SYSTEM_PROMPT},
        {"role": "user", "content": user_prompt},
    ]
    return llm.invoke(messages).strip()