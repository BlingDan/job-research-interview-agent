from textwrap import dedent

from app.core.llm import JobResearchLLM
from app.schemas.report import SearchResultItem
from app.schemas.state import TodoItem


SUMMARIZER_SYSTEM_PROMPT = dedent(
    """
    你是一个任务级研究总结 Agent。
    你的任务是把一个 TODO 的搜索结果压缩成结构化研究笔记。

    输出要求：
    1. 只返回 JSON 对象
    2. 不要返回 Markdown 代码块
    3. 不要编造来源
    4. 只基于给定搜索结果总结
    5. 输出字段必须包含：
       - question_answered
       - key_points
       - open_questions
       - needs_followup
       - followup_queries
       - sources
    """
).strip()

def generate_summary_text(
    todo: TodoItem,
    results: list[SearchResultItem],
    local_context: str | None = None
) -> str:
    llm = JobResearchLLM(
        temperature=0.2,
        max_tokens=1800,
    )

    user_prompt = dedent(
        f"""
        当前任务：
        - 标题：{todo.title}
        - 研究意图：{todo.intent}
        - 查询语句：{todo.query}
        - 类别：{todo.category or "unknown"}

        候选人本地上下文（可选）：
        {local_context or "未提供"}

        搜索结果如下：
        {_render_results(results)}

        请基于这些结果输出任务级结构化总结。
        如果信息仍不完整，可以把后续要补搜的问题写到 open_questions 和 followup_queries 中。
        """
    ).strip()

    messages = [
        {"role": "system", "content": SUMMARIZER_SYSTEM_PROMPT},
        {"role": "user", "content": user_prompt},
    ]
    
    return llm.invoke(messages).strip()

def _render_results(results: list[SearchResultItem]) -> str:
    blocks: list[str] = []

    for index, item in enumerate(results, start=1):
        blocks.append(
            "\n".join(
                [
                    f"[结果 {index}]",
                    f"标题：{item.title}",
                    f"摘要：{item.snippet}",
                    f"来源：{item.source}",
                ]
            )
        )
    return "\n\n".join(blocks)