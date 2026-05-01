from __future__ import annotations

from app.schemas.agent_pilot import AgentPilotTask, RevisionRecord, RouteSource


FALLBACK_NOTICE = "（提示：当前通过本地规则解析意图，LLM 路由暂不可用，结果可能不够精准。）"


def with_fallback_notice(reply: str, route_source: RouteSource | None) -> str:
    if route_source == "fallback":
        return f"{FALLBACK_NOTICE}\n\n{reply}"
    return reply


def format_planning_ack() -> str:
    return "已收到需求，Planner Agent 正在解析意图、拆解任务和选择飞书工具。稍等片刻，我会在这条消息里更新执行计划。"


def format_plan_reply(task: AgentPilotTask) -> str:
    if not task.plan:
        return "已收到任务，但计划尚未生成。"

    lines = ["已理解需求，我会按下面计划执行：", ""]
    for index, step in enumerate(task.plan.steps, start=1):
        artifact = f" -> {step.expected_artifact}" if step.expected_artifact else ""
        lines.append(f"{index}. {step.title}：{step.goal}{artifact}")
    lines.extend(["", task.plan.confirmation_prompt])
    return "\n".join(lines)


def format_plan_reply_chunks(task: AgentPilotTask) -> list[str]:
    if not task.plan:
        return [format_plan_reply(task)]

    chunks = ["已理解需求，正在拆解执行计划..."]
    lines = ["已理解需求，我会按下面计划执行：", ""]
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


def format_final_reply(task: AgentPilotTask) -> str:
    lines = ["任务已完成，成果如下："]
    for artifact in task.artifacts:
        link = artifact.url or artifact.local_path or "暂无链接"
        lines.append(f"- {artifact.title}: {link}")
    lines.append("")
    lines.append("你可以继续在当前 IM 里发送「修改：...」来迭代内容。")
    return "\n".join(lines)


def format_revision_reply(task: AgentPilotTask, revision: RevisionRecord) -> str:
    targets = "、".join(revision.target_artifacts) or "相关产物"
    return f"已处理修改：{revision.instruction}\n影响范围：{targets}\n{format_progress_reply(task)}"


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
            "- 直接发送办公协同任务：生成方案文档、5 页答辩材料和画板",
            "- 确认：开始执行当前计划",
            "- 当前进度 / /status：查看当前任务状态",
            "- 修改：...：按你的反馈迭代产物，也可以不加「修改：」直接说要改哪个文档、PPT 或画板",
            "- /reset：清除当前聊天绑定的任务上下文（有任务时会先确认）",
            "- 确认重置：确认执行重置",
            "- /help：查看命令",
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


def _next_action(task: AgentPilotTask) -> str:
    if task.status == "WAITING_CONFIRMATION":
        return "等待你回复「确认」。"
    if task.status == "DONE":
        return "可以继续发送「修改：...」迭代产物。"
    if task.status == "FAILED":
        return "查看错误后重试。"
    return "Agent 正在继续执行。"
