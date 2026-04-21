"""
组织prompt，调用planner agent,返回原始结果
"""

from __future__ import annotations

from textwrap import dedent
from datetime import datetime

from app.core.llm import JobResearchLLM
from app.schemas.task import TaskCreateRequest

PLANNER_SYSTEM_PROMPT = dedent(
    """
    你是一个求职研究 Planner Agent。
    你的任务是把用户输入拆成 3 到 5 个高质量研究 TODO。

    输出要求：
    1. 只返回 JSON 数组
    2. 不要返回 Markdown 代码块
    3. 不要返回解释
    4. 每个对象必须包含：
       - title
       - intent
       - query
       - category
    5. category 只允许使用：
       - jd
       - company
       - interview
       - candidate_gap
    """
).strip()

def _safe_text(val: str| None, default: str = "Not Supplied") -> str:
    text = (val or "").strip()
    return text if text else default

def _build_user_prompt(payload: TaskCreateRequest) -> str:
    today = datetime.now().strftime("%Y-%m-%d")
    return dedent(
        f"""
        今天日期：{today}

        研究输入：
        - 岗位 JD：{_safe_text(payload.jd_text)}
        - 公司：{_safe_text(payload.company_name)}
        - 面试主题：{_safe_text(payload.interview_topic)}
        - 本地资料路径：{_safe_text(payload.local_context_path)}
        - 用户补充：{_safe_text(payload.user_note)}

        请把这个求职研究任务拆成 3 到 5 个 TODO。

        覆盖要求：
        1. 岗位核心能力
        2. 公司/业务/团队背景
        3. 高频技术面试点
        4. 候选人准备方向或差距

        query 必须适合公开搜索引擎检索。
        category 只能从 jd/company/interview/candidate_gap 中选择。
    )
    """
    ).strip()


def generate_planning_text(payload: TaskCreateRequest) -> str:
    llm = JobResearchLLM(
        temperature=0.2,
        max_tokens=2048,
    )
    messages = [
        {"role":"system", "content": PLANNER_SYSTEM_PROMPT},
        {"role":"user", "content": _build_user_prompt(payload)},
    ]

    return llm.invoke(messages).strip()
