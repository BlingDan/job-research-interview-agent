import type { ArtifactPreview, TaskAction, TaskDetail } from "../types";
import { ArtifactPreviewPanel } from "./ArtifactPreviewPanel";
import { ExecutionTimelinePanel } from "./ExecutionTimelinePanel";
import { PendingActionsPanel } from "./PendingActionsPanel";

interface TaskDetailPageProps {
  task: TaskDetail | null;
  preview: ArtifactPreview | null;
  selectedKind: string | null;
  onSelectKind: (kind: "doc" | "slides" | "canvas") => void;
  onAction: (action: TaskAction) => void;
}

export function TaskDetailPage({
  task,
  preview,
  selectedKind,
  onSelectKind,
  onAction,
}: TaskDetailPageProps) {
  if (!task) {
    return (
      <section className="panel detail-panel empty-detail">
        <p>Select a task from the left to inspect the unified assistant state.</p>
      </section>
    );
  }

  const actions: TaskAction[] =
    task.status === "WAITING_CONFIRMATION"
      ? [
          {
            type: "confirm",
            label: "Confirm task",
            task_id: task.task_id,
            description: "Continue the current plan.",
            endpoint: `/api/assistant/tasks/${task.task_id}/actions/confirm`,
          },
          {
            type: "reset",
            label: "Reset binding",
            task_id: task.task_id,
            description: "Clear the current IM binding.",
            endpoint: `/api/assistant/tasks/${task.task_id}/actions/reset`,
          },
        ]
      : [
          {
            type: "revise",
            label: "Request revision",
            task_id: task.task_id,
            description: "Create a targeted artifact update.",
            endpoint: `/api/assistant/tasks/${task.task_id}/actions/revise`,
          },
        ];

  return (
    <section className="detail-column">
      <section className="panel detail-panel">
        <div className="panel-header">
          <div>
            <p className="eyebrow">Unified Assistant</p>
            <h2>{task.task_id}</h2>
          </div>
          <span className="badge">{task.status}</span>
        </div>
        <p className="detail-summary">{task.plan?.summary || task.reply || "Task detail is available once planning starts."}</p>
      </section>

      <PendingActionsPanel actions={actions} onAction={onAction} />

      <ArtifactPreviewPanel
        artifacts={task.artifacts}
        selectedKind={selectedKind}
        onSelectKind={onSelectKind}
        preview={preview}
      />

      <ExecutionTimelinePanel
        plan={task.plan}
        toolExecutions={task.tool_executions}
        revisions={task.revisions}
      />
    </section>
  );
}
