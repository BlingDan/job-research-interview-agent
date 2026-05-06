from __future__ import annotations

import concurrent.futures
import json
import re
from textwrap import dedent

from app.core.config import get_settings
from app.core.llm import JobResearchLLM
from app.core.logging import get_logger
from app.schemas.agent_pilot import AgentPlan, ChatMessage, PlanStep
from app.integrations.artifacts.tool_registry import build_default_tool_plan

logger = get_logger()

SCENARIO_TEMPLATES: dict[str, dict] = {
    "周报": {
        "keywords": ["周报", "weekly report", "本周总结", "工作周报", "weekly"],
        "structure": "本周完成 / 下周计划 / 风险与阻塞 / 需要协助",
        "tone": "精炼、数据驱动、结论先行",
        "doc_sections": ["本周工作摘要", "重点项目进展", "数据指标", "下周计划", "风险与求助"],
        "slides_pages": 3,
    },
    "方案设计": {
        "keywords": ["方案", "设计", "技术方案", "架构设计", "方案设计", "proposal", "design"],
        "structure": "背景与目标 / 方案对比 / 架构设计 / 实施计划 / 风险评估",
        "tone": "结构化、论证充分、有对比分析",
        "doc_sections": ["背景与目标", "方案对比分析", "架构设计", "关键技术细节", "实施计划与里程碑", "风险评估与应对"],
        "slides_pages": 5,
    },
    "评审": {
        "keywords": ["评审", "答辩", "汇报", "review", "演示", "presentation"],
        "structure": "项目概述 / 核心亮点 / 技术方案 / 数据验证 / 未来规划",
        "tone": "说服力强、突出亮点、数据支撑",
        "doc_sections": ["项目概述", "核心创新点", "技术方案详解", "实验数据与效果", "未来演进方向"],
        "slides_pages": 5,
    },
    "会议纪要": {
        "keywords": ["会议纪要", "会议记录", "meeting", "讨论", "纪要", "minutes"],
        "structure": "会议信息 / 讨论议题 / 决策结论 / 待办事项 / 下次议程",
        "tone": "客观、准确、可追溯",
        "doc_sections": ["会议基本信息", "讨论议题与结论", "待办事项(Owner+DDL)", "下次会议安排"],
        "slides_pages": 0,
    },
    "OKR复盘": {
        "keywords": ["OKR", "复盘", "目标", "关键结果", "retrospective", "季度总结"],
        "structure": "OKR 回顾 / 达成情况 / 根因分析 / 经验教训 / 下周期 OKR",
        "tone": "坦诚、自省、行动导向",
        "doc_sections": ["本周期 OKR 回顾", "达成情况与数据", "未达成根因分析", "经验与教训", "下周期 OKR 建议"],
        "slides_pages": 4,
    },
}


def _build_scenario_reference() -> str:
    lines: list[str] = []
    for name, tmpl in SCENARIO_TEMPLATES.items():
        lines.append(
            f"- {name}: 触发词=[{', '.join(tmpl['keywords'][:4])}] "
            f"结构={tmpl['structure']} "
            f"语气={tmpl['tone']} "
            f"文档章节=[{' / '.join(tmpl['doc_sections'][:5])}] "
            f"Slides页={tmpl['slides_pages']}"
        )
    return "\n".join(lines)


AGENT_PILOT_PLANNER_SYSTEM_PROMPT = dedent(
    f"""
    你是 Agent-Pilot 的 Planner Agent。
    你的目标是把飞书 IM 中的办公协同需求拆成可执行计划，并明确需要调用的飞书办公套件。

    必须覆盖官方 A-F 场景：
    A 意图/指令入口：从飞书 IM 捕捉自然语言需求。
    B 任务理解和规划：拆解阶段、Agent、工具和交付物。
    C Doc/Whiteboard 生成：生成方案文档和画板/白板图。
    D Presentation 生成：生成汇报演示文稿。
    E 多端协同：桌面端/移动端共享同一 IM 任务状态和产物链接。
    F 总结交付：最终回到 IM 汇总成果和后续修改入口。

    可参考以下场景模板，根据用户消息自行判断最匹配的场景（也可不匹配任何模板）：

    {_build_scenario_reference()}

    只返回 JSON 对象，不要返回 Markdown。
    JSON 字段：
    - summary: 一句话说明计划
    - confidence: 0.0 到 1.0，表示对需求理解的置信度。
      * >0.9：需求非常明确（如"帮我写周报"），可以直接执行
      * 0.7-0.9：基本明确但缺少部分细节（如"准备评审材料"但没说评审什么）
      * <0.7：需求模糊（如"帮我准备一些材料"），需要追问澄清
    - clarification_questions: 字符串数组。当 confidence<0.7 时，列出 1-3 个需要向用户确认的问题。
      当 confidence>=0.7 时为空数组。
    - confirmation_prompt: 请用户回复「确认」继续。当 confidence>0.9 时可为空字符串。
    - detected_template: 识别到的场景模板名称（周报/方案设计/评审/会议纪要/OKR复盘），无匹配则为空。
    - steps: 数组，每个对象包含 id/title/goal/agent/tool/expected_artifact
    - tool_plan 可省略；系统会补充标准飞书工具计划
    """
).strip()


def _fallback_match_scenario(user_message: str) -> str | None:
    lower = user_message.lower()
    for name, template in SCENARIO_TEMPLATES.items():
        for keyword in template["keywords"]:
            if keyword in user_message or keyword.lower() in lower:
                return name
    return None


def build_agent_plan(user_message: str, chat_history: list[ChatMessage] | None = None) -> AgentPlan:
    settings = get_settings()
    mode = getattr(settings, "agent_pilot_planner_mode", "fallback")
    if mode == "fallback":
        logger.info("Planner mode=fallback, using built-in plan.")
        return build_fallback_plan(user_message, chat_history)

    try:
        return build_llm_agent_plan(user_message, chat_history)
    except Exception:
        logger.warning("Planner LLM call failed, falling back to built-in plan.", exc_info=True)
        if mode == "llm":
            raise
        return build_fallback_plan(user_message, chat_history)


def build_llm_agent_plan(
    user_message: str, chat_history: list[ChatMessage] | None = None
) -> AgentPlan:
    llm = JobResearchLLM(
        temperature=0.2,
        max_tokens=2048,
    )
    messages: list[dict[str, str]] = [
        {"role": "system", "content": AGENT_PILOT_PLANNER_SYSTEM_PROMPT},
        {"role": "user", "content": _build_agent_pilot_user_prompt(user_message, chat_history)},
    ]
    settings = get_settings()
    planner_timeout = getattr(settings, "agent_pilot_planner_timeout_seconds", 20.0)
    with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
        future = pool.submit(llm.invoke, messages)
        try:
            raw = future.result(timeout=planner_timeout).strip()
        except concurrent.futures.TimeoutError:
            raise RuntimeError(
                f"Planner LLM timed out after {planner_timeout:.0f}s"
            )
    return parse_plan_output(raw)


def _build_agent_pilot_user_prompt(
    user_message: str, chat_history: list[ChatMessage] | None = None
) -> str:
    parts: list[str] = []

    if chat_history:
        parts.append("群聊上下文（最近的消息）：")
        for msg in chat_history:
            sender = msg.sender_name or "未知用户"
            parts.append(f"  [{sender}]: {msg.content}")
        parts.append("")

    parts.append(f"飞书 IM 当前需求：\n{user_message}")
    parts.append("")

    prompt_lines = [
        "请生成 Agent-Pilot 的执行计划。要求：",
        "1. 步骤数量 4 到 6 步，体现 PlannerAgent、DocAgent、PresentationAgent、CanvasAgent、DeliveryService。",
        "2. 每一步写清楚 goal、agent、tool 和 expected_artifact。",
        "3. tool 优先使用 Feishu IM、Feishu Doc、Feishu Slides、Feishu Canvas/Whiteboard。",
        "4. 评估 confidence：需求明确(>0.9)、基本明确(0.7-0.9)、模糊(<0.7)。",
        "5. confidence<0.7 时提供 1-3 个 clarification_questions，先追问再规划。",
        "6. 如果有群聊上下文，必须引用讨论中的关键决策、争议点、结论。",
        "7. summary 要体现飞书原生、多端协同和 Agent 编排能力。",
        "8. 参考 system prompt 中的场景模板，自行判断用户的办公协同需求匹配哪个场景。",
        "   如果匹配到模板，按照该模板的结构和语气组织内容。",
    ]

    parts.extend(prompt_lines)
    return "\n".join(parts)


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

    raw_confidence = data.get("confidence", 0.5)
    try:
        confidence = min(max(float(raw_confidence), 0.0), 1.0)
    except (TypeError, ValueError):
        confidence = 0.5

    raw_questions = data.get("clarification_questions", [])
    clarification_questions: list[str] = []
    if isinstance(raw_questions, list):
        for q in raw_questions:
            if isinstance(q, str) and q.strip():
                clarification_questions.append(q.strip())

    return AgentPlan(
        summary=str(data.get("summary") or "已生成 Agent-Pilot 执行计划。").strip(),
        steps=steps,
        confirmation_prompt=str(
            data.get("confirmation_prompt") or "回复「确认」后我开始生成文档、汇报材料和画板。"
        ).strip(),
        tool_plan=build_default_tool_plan(),
        confidence=confidence,
        clarification_questions=clarification_questions,
    )


def build_fallback_plan(
    user_message: str, chat_history: list[ChatMessage] | None = None
) -> AgentPlan:
    template_name = _fallback_match_scenario(user_message)

    if template_name == "周报":
        summary = "我会根据本周工作内容生成结构化周报，包含完成事项、下周计划和风险求助。"
    elif template_name == "评审":
        summary = "我会生成项目评审材料，包含核心亮点、技术方案、数据验证和未来规划。"
    elif template_name == "会议纪要":
        summary = "我会根据讨论内容整理会议纪要，提取关键决策和待办事项。"
    elif template_name == "OKR复盘":
        summary = "我会生成 OKR 复盘文档，分析达成情况、根因和经验教训。"
    else:
        summary = "我会把 IM 需求编排为项目方案文档、汇报演示文稿和架构画板，并在同一聊天中交付。"

    fallback_steps = _build_fallback_steps(template_name)

    chat_context_note = ""
    if chat_history:
        senders = {msg.sender_name for msg in chat_history if msg.sender_name}
        chat_context_note = f"（已参考 {len(chat_history)} 条群聊上下文，参与人：{', '.join(senders)}）"

    return AgentPlan(
        summary=f"{summary}{chat_context_note}",
        steps=fallback_steps,
        confirmation_prompt="回复「确认」后我开始生成文档、汇报材料和画板。",
        tool_plan=build_default_tool_plan(),
        confidence=0.85 if template_name else 0.6,
        clarification_questions=[],
    )


def _build_fallback_steps(template_name: str | None) -> list[PlanStep]:
    if template_name == "周报":
        return [
            PlanStep(id="step-1", title="意图解析与本周工作梳理", goal="提取本周重点工作和数据", agent="PlannerAgent", tool="Feishu IM"),
            PlanStep(id="step-2", title="生成结构化周报", goal="按「完成/计划/风险/求助」结构生成周报文档", agent="DocAgent", tool="Feishu Doc", expected_artifact="结构化周报"),
            PlanStep(id="step-3", title="生成周报摘要卡片", goal="将关键数据可视化为 Slides 摘要", agent="PresentationAgent", tool="Feishu Slides", expected_artifact="周报摘要 Slides"),
            PlanStep(id="step-4", title="生成数据趋势画板", goal="用 Canvas 展示本周关键指标变化趋势", agent="CanvasAgent", tool="Feishu Canvas/Whiteboard", expected_artifact="数据趋势画板"),
            PlanStep(id="step-5", title="交付与后续安排", goal="推送产物链接并建议下周改进方向", agent="DeliveryService", tool="Feishu IM", expected_artifact="最终交付消息"),
        ]
    if template_name == "评审":
        return [
            PlanStep(id="step-1", title="需求理解与评审角度分析", goal="从评委视角分析项目应突出的亮点和论证链", agent="PlannerAgent", tool="Feishu IM"),
            PlanStep(id="step-2", title="生成答辩方案文档", goal="按「概述/创新/方案/数据/演进」结构生成评审文档", agent="DocAgent", tool="Feishu Doc", expected_artifact="答辩方案文档"),
            PlanStep(id="step-3", title="生成汇报 Slides", goal="突出核心创新点和数据支撑，说服评委", agent="PresentationAgent", tool="Feishu Slides", expected_artifact="汇报演示文稿"),
            PlanStep(id="step-4", title="生成方案架构画板", goal="用 Canvas 展示技术架构和数据流", agent="CanvasAgent", tool="Feishu Canvas/Whiteboard", expected_artifact="架构画板"),
            PlanStep(id="step-5", title="交付与模拟建议", goal="推送产物链接，附上答辩建议和可能的质疑点", agent="DeliveryService", tool="Feishu IM", expected_artifact="最终交付消息"),
        ]
    if template_name == "会议纪要":
        return [
            PlanStep(id="step-1", title="讨论要点提取", goal="从群聊中提取讨论议题、决策和待办", agent="PlannerAgent", tool="Feishu IM"),
            PlanStep(id="step-2", title="生成会议纪要文档", goal="按「信息/议题/决策/待办」结构生成纪要", agent="DocAgent", tool="Feishu Doc", expected_artifact="会议纪要文档"),
            PlanStep(id="step-3", title="生成待办追踪看板", goal="用 Canvas 展示待办事项的 Owner 和 DDL", agent="CanvasAgent", tool="Feishu Canvas/Whiteboard", expected_artifact="待办追踪画板"),
            PlanStep(id="step-4", title="生成会议摘要消息", goal="将关键结论和待办以结构化消息推送到 IM", agent="DeliveryService", tool="Feishu IM", expected_artifact="会议摘要交付"),
        ]
    if template_name == "OKR复盘":
        return [
            PlanStep(id="step-1", title="OKR 数据梳理", goal="分析 OKR 达成数据和关键变化", agent="PlannerAgent", tool="Feishu IM"),
            PlanStep(id="step-2", title="生成复盘文档", goal="按「回顾/达成/根因/教训/下周期」结构生成复盘文档", agent="DocAgent", tool="Feishu Doc", expected_artifact="OKR复盘文档"),
            PlanStep(id="step-3", title="生成复盘 Slides", goal="将关键数据和洞察可视化", agent="PresentationAgent", tool="Feishu Slides", expected_artifact="复盘汇报 Slides"),
            PlanStep(id="step-4", title="生成 OKR 仪表盘画板", goal="用 Canvas 展示 OKR 进度和趋势", agent="CanvasAgent", tool="Feishu Canvas/Whiteboard", expected_artifact="OKR仪表盘画板"),
            PlanStep(id="step-5", title="交付与行动建议", goal="推送产物链接并给出下周期改进建议", agent="DeliveryService", tool="Feishu IM", expected_artifact="最终交付消息"),
        ]
    return [
        PlanStep(id="step-1", title="意图捕捉与任务规划", goal="理解 IM 需求，拆解 Agent-Pilot 交付物和执行顺序。", agent="PlannerAgent", tool="Feishu IM", expected_artifact="确认计划"),
        PlanStep(id="step-2", title="生成项目方案文档", goal="围绕 Agent 编排、多端协同、飞书办公套件联动和工程实现生成方案。", agent="DocAgent", tool="Feishu Doc", expected_artifact="项目方案文档"),
        PlanStep(id="step-3", title="生成汇报演示文稿", goal="把方案浓缩成适合项目汇报的 Slides。", agent="PresentationAgent", tool="Feishu Slides", expected_artifact="汇报演示文稿"),
        PlanStep(id="step-4", title="生成架构画板", goal="用 Canvas/Whiteboard 展示 IM、Agent、Doc、Slides 与交付闭环。", agent="CanvasAgent", tool="Feishu Canvas/Whiteboard", expected_artifact="Agent 编排架构图"),
        PlanStep(id="step-5", title="IM 总结交付", goal="把所有 artifact 链接、摘要和后续修改入口发送回同一 Feishu 聊天。", agent="DeliveryService", tool="Feishu IM", expected_artifact="最终交付消息"),
    ]
