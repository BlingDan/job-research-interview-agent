from __future__ import annotations

from app.schemas.agent_pilot import AgentPilotTask, RevisionRecord, RouteSource


FALLBACK_NOTICE = "（提示：当前通过本地规则解析意图，LLM 路由暂不可用，结果可能不够精准。）"


def with_fallback_notice(reply: str, route_source: RouteSource | None) -> str:
    if route_source == "fallback":
        return f"{FALLBACK_NOTICE}\n\n{reply}"
    return reply


def format_planning_ack() -> str:
    return "已收到需求，Planner Agent 正在解析意图、拆解任务和选择飞书工具。稍等片刻，我会在这条消息里更新执行计划。"


def format_auto_execute_reply(task: AgentPilotTask) -> str:
    if not task.plan:
        return "已收到任务，正在执行..."
    lines = [f"已理解需求（置信度 {task.plan.confidence:.0%}），正在按以下计划直接执行：", ""]
    for index, step in enumerate(task.plan.steps, start=1):
        artifact = f" -> {step.expected_artifact}" if step.expected_artifact else ""
        lines.append(f"{index}. {step.title}：{step.goal}{artifact}")
    lines.extend(["", "产物生成中，请稍候..."])
    return "\n".join(lines)


def format_countdown_reply(task: AgentPilotTask, seconds: int) -> str:
    if not task.plan:
        return format_plan_reply(task)
    lines = [f"已理解需求（置信度 {task.plan.confidence:.0%}），计划如下：", ""]
    for index, step in enumerate(task.plan.steps, start=1):
        artifact = f" -> {step.expected_artifact}" if step.expected_artifact else ""
        lines.append(f"{index}. {step.title}：{step.goal}{artifact}")
    lines.extend([
        "",
        f"将在 {seconds} 秒后自动执行。回复「确认」立即开始，回复其他内容取消。",
    ])
    return "\n".join(lines)


def format_countdown_expired_reply() -> str:
    return "倒计时结束，自动开始执行计划..."


def format_clarification_reply(task: AgentPilotTask) -> str:
    if not task.plan:
        return "已收到任务，但计划尚未生成。"
    lines = ["收到你的需求，在开始执行前想确认几个细节：", ""]
    for index, q in enumerate(task.plan.clarification_questions, start=1):
        lines.append(f"{index}. {q}")
    lines.extend(["", "请回复你的答案，我会据此生成更精准的计划。"])
    return "\n".join(lines)


def format_plan_reply(task: AgentPilotTask) -> str:
    if not task.plan:
        return "已收到任务，但计划尚未生成。"

    lines = [f"已理解需求（置信度 {task.plan.confidence:.0%}），我会按下面计划执行：", ""]
    for index, step in enumerate(task.plan.steps, start=1):
        artifact = f" -> {step.expected_artifact}" if step.expected_artifact else ""
        lines.append(f"{index}. {step.title}：{step.goal}{artifact}")
    lines.extend(["", task.plan.confirmation_prompt])
    return "\n".join(lines)


def format_plan_reply_chunks(task: AgentPilotTask) -> list[str]:
    if not task.plan:
        return [format_plan_reply(task)]

    chunks = ["已理解需求，正在拆解执行计划..."]
    lines = [f"已理解需求（置信度 {task.plan.confidence:.0%}），我会按下面计划执行：", ""]
    for index, step in enumerate(task.plan.steps, start=1):
        artifact = f" -> {step.expected_artifact}" if step.expected_artifact else ""
        lines.append(f"{index}. {step.title}：{step.goal}{artifact}")
        chunks.append("\n".join(lines))
    lines.extend(["", task.plan.confirmation_prompt])
    chunks.append("\n".join(lines))
    return chunks


def format_progress_reply(task: AgentPilotTask) -> str:
    lines = [f"当前状态：{task.status}"]
    if task.artifacts:
        lines.append("已完成产物：")
        for artifact in task.artifacts:
            link = artifact.url or artifact.local_path or "暂无链接"
            lines.append(f"- {artifact.title}: {link}")
    else:
        lines.append("暂未生成产物。")
    lines.append(f"下一步：{_next_action(task)}")
    return "\n".join(lines)


_ARTIFACT_EMOJI: dict[str, str] = {"doc": "\U0001F4C4", "slides": "\U0001F4CA", "canvas": "\U0001F3A8"}
_ARTIFACT_LABEL: dict[str, str] = {"doc": "Doc 方案", "slides": "Slides 汇报", "canvas": "Canvas 架构图"}


def format_generating_card(artifact_statuses: dict[str, str]) -> str:
    lines = []
    for kind in ("doc", "slides", "canvas"):
        emoji = _ARTIFACT_EMOJI.get(kind, "\U0001F4CC")
        label = _ARTIFACT_LABEL.get(kind, kind)
        status = artifact_statuses.get(kind, "生成中...")
        lines.append(f"{emoji} **{label}**：{status}")
    lines.append("")
    lines.append("请稍候，产物将逐一更新...")
    return "\n".join(lines)


def format_final_reply(task: AgentPilotTask, *, product_mode: bool = False) -> str:
    lines = ["✅ 任务已完成，成果如下："]
    for artifact in task.artifacts:
        emoji = _ARTIFACT_EMOJI.get(artifact.kind, "")
        link = artifact.url or artifact.local_path or "暂无链接"
        lines.append(f"{emoji} **{artifact.title}**：{link}")
    if task.artifacts:
        lines.append("")
    lines.append("✏️ 发送「修改：...」继续迭代 | 📊 发送「现在做到哪了？」查看状态")
    if product_mode:
        lines.append("🎭 发送「排练」让 Agent 扮演评委/老板/客户模拟答辩 Q&A")
        lines.append("📋 发送「历史」查看本聊天的历史任务")
    return "\n".join(lines)


def format_revision_reply(task: AgentPilotTask, revision: RevisionRecord) -> str:
    targets = "、".join(revision.target_artifacts) or "相关产物"
    lines = [
        f"✅ 已处理修改：{revision.instruction}",
        f"影响范围：{targets}",
    ]
    if revision.change_detail:
        lines.append("")
        lines.append("变更摘要：")
        for detail_line in revision.change_detail.split("\n"):
            if detail_line.strip():
                lines.append(f"  • {detail_line.strip()}")
    lines.append("")
    lines.append(format_progress_reply(task))
    return "\n".join(lines)


def format_revision_clarification_reply(task: AgentPilotTask, instruction: str) -> str:
    available = "、".join(artifact.kind for artifact in task.artifacts) or "doc、slides、canvas"
    return (
        f"我收到了修改需求：{instruction}\n"
        f"请说明要修改哪个产物：{available}。例如「修改：文档最后一行添加时间」"
        "或「修改：PPT 第 5 页突出工程实现」。"
    )


def format_error_reply(task: AgentPilotTask) -> str:
    return f"任务在 {task.status} 阶段失败：{task.error or '未知错误'}。请稍后重试或发送新的修改指令。"


def format_help_reply() -> str:
    return "\n".join(
        [
            "Agent-Pilot 可用命令：",
            "- 直接发送办公协同任务：生成方案文档、汇报材料和画板",
            "- 短指令模板：周报 | 方案设计 | 评审 | 会议纪要 | OKR复盘",
            "- 确认：开始执行当前计划",
            "- 当前进度 / /status：查看当前任务状态",
            "- 添加、修改：...：按你的反馈迭代产物",
            "- /reset：清除当前聊天绑定的任务上下文",
            "- 确认重置：确认执行重置",
            "- /help：查看命令",
            "- 排练：让 Agent 扮演评委模拟答辩 Q&A",
            "- 历史：查看历史任务",
        ]
    )


def format_reset_reply() -> str:
    return "已重置当前聊天的任务上下文。你可以重新发送一个办公协同任务。"


def format_reset_confirm_reply(task: AgentPilotTask) -> str:
    plan_summary = ""
    if task.plan:
        plan_summary = f"「{task.plan.summary}」"
    return (
        f"当前有进行中的任务{plan_summary}（当前状态：{task.status}），"
        "确认要重置吗？回复「确认重置」继续，回复其他内容取消。"
    )


def format_reset_expired_reply() -> str:
    return "此重置指令已过期，当前有更新且进行中的任务。如需重置请重新发送。"


def format_no_active_task_reply() -> str:
    return "当前没有活跃任务。请直接发送一个办公协同需求，或发送 /help 查看可用命令。"


def format_feedback_prompt() -> str:
    return "这些结果对你有帮助吗？ 👍 有帮助 / 👎 需要改进"


def format_feedback_thanks(rating: str) -> str:
    if rating == "helpful":
        return "感谢反馈！我会继续保持这个水平。"
    return "感谢反馈！我会努力改进。你可以发送「修改：...」告诉我具体哪里需要调整。"


def format_rehearse_reply(questions_text: str) -> str:
    lines = ["🎭 **答辩排练模式**", ""]
    lines.append("以下是针对你的方案提出的评审问题：")
    lines.append("")
    lines.append(questions_text)
    lines.append("")
    lines.append("你可以逐条回复，我会帮你把好的回答更新进方案中。")
    return "\n".join(lines)


def _next_action(task: AgentPilotTask) -> str:
    if task.status == "WAITING_CONFIRMATION":
        return "等待你回复「确认」。"
    if task.status == "DONE":
        return "可以继续发送「修改：...」迭代产物，或发送「排练」模拟答辩。"
    if task.status == "FAILED":
        return "查看错误后重试。"
    return "Agent 正在继续执行。"
