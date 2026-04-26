from __future__ import annotations

from app.schemas.agent_pilot import AgentPilotTask, RevisionRecord


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


def format_error_reply(task: AgentPilotTask) -> str:
    return f"任务在 {task.status} 阶段失败：{task.error or '未知错误'}。请稍后重试或发送新的修改指令。"


def _next_action(task: AgentPilotTask) -> str:
    if task.status == "WAITING_CONFIRMATION":
        return "等待你回复「确认」。"
    if task.status == "DONE":
        return "可以继续发送「修改：...」迭代产物。"
    if task.status == "FAILED":
        return "查看错误后重试。"
    return "Agent 正在继续执行。"
