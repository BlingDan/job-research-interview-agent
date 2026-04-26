"""
组织prompt，调用planner agent,返回原始结果
"""

from __future__ import annotations

from textwrap import dedent
from datetime import datetime
import json
import re
from typing import Any

from app.core.llm import JobResearchLLM
from app.schemas.agent_pilot import AgentPlan, PlanStep
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


AGENT_PILOT_PLANNER_SYSTEM_PROMPT = dedent(
    """
    你是 Agent-Pilot 的 Planner Agent。
    你的目标是把飞书 IM 中的办公协同需求拆成可执行计划，并明确需要调用的飞书办公套件。

    只返回 JSON 对象，不要返回 Markdown。
    JSON 字段：
    - summary: 一句话说明计划
    - confirmation_prompt: 请用户回复「确认」继续
    - steps: 数组，每个对象包含 id/title/goal/agent/tool/expected_artifact
    """
).strip()


def build_agent_plan(user_message: str) -> AgentPlan:
    # The competition demo must be stable even without LLM credentials, so the
    # deterministic plan is the default executable behavior.
    return build_fallback_plan(user_message)


def parse_plan_output(raw_text: str) -> AgentPlan:
    text = raw_text.strip()
    if not text:
        raise ValueError("Planner returned empty text.")

    try:
        data = json.loads(text)
    except json.JSONDecodeError:
        fenced_match = re.search(r"```json\s*(.*?)\s*```", text, re.DOTALL | re.IGNORECASE)
        if not fenced_match:
            object_match = re.search(r"({.*})", text, re.DOTALL)
            if not object_match:
                raise ValueError("Failed to extract planner JSON object.")
            data = json.loads(object_match.group(1))
        else:
            data = json.loads(fenced_match.group(1).strip())

    if not isinstance(data, dict):
        raise ValueError("Planner output must be a JSON object.")

    steps = [
        PlanStep(
            id=str(item.get("id") or f"step-{index}"),
            title=str(item.get("title") or "").strip(),
            goal=str(item.get("goal") or "").strip(),
            agent=str(item.get("agent") or "").strip(),
            tool=str(item.get("tool") or "").strip(),
            expected_artifact=(str(item.get("expected_artifact")).strip() if item.get("expected_artifact") else None),
        )
        for index, item in enumerate(data.get("steps", []), start=1)
        if isinstance(item, dict)
    ]
    if not steps:
        raise ValueError("Planner output must include steps.")

    return AgentPlan(
        summary=str(data.get("summary") or "已生成 Agent-Pilot 执行计划。").strip(),
        steps=steps,
        confirmation_prompt=str(
            data.get("confirmation_prompt") or "回复「确认」后我开始生成文档、汇报材料和画板。"
        ).strip(),
    )


def build_fallback_plan(user_message: str) -> AgentPlan:
    return AgentPlan(
        summary="我会把 IM 需求编排为参赛方案文档、5 页答辩材料和架构画板，并在同一聊天中交付。",
        steps=[
            PlanStep(
                id="step-1",
                title="意图捕捉与任务规划",
                goal="理解 IM 需求，拆解 Agent-Pilot 参赛交付物和执行顺序。",
                agent="PlannerAgent",
                tool="Feishu IM",
                expected_artifact="确认计划",
            ),
            PlanStep(
                id="step-2",
                title="生成参赛方案文档",
                goal="围绕 Agent 编排、多端协同、飞书办公套件联动和工程实现生成方案。",
                agent="DocAgent",
                tool="Feishu Doc",
                expected_artifact="参赛方案文档",
            ),
            PlanStep(
                id="step-3",
                title="生成 5 页答辩汇报材料",
                goal="把方案浓缩成适合比赛答辩的 5 页 Slides。",
                agent="PresentationAgent",
                tool="Feishu Slides",
                expected_artifact="5 页答辩汇报材料",
            ),
            PlanStep(
                id="step-4",
                title="生成架构画板",
                goal="用 Canvas/Whiteboard 展示 IM、Agent、Doc、Slides 与交付闭环。",
                agent="CanvasAgent",
                tool="Feishu Canvas/Whiteboard",
                expected_artifact="Agent 编排架构图",
            ),
            PlanStep(
                id="step-5",
                title="IM 总结交付",
                goal="把所有 artifact 链接、摘要和后续修改入口发送回同一 Feishu 聊天。",
                agent="DeliveryService",
                tool="Feishu IM",
                expected_artifact="最终交付消息",
            ),
        ],
        confirmation_prompt="回复「确认」后我开始生成参赛方案文档、5 页答辩材料和架构画板。",
    )
