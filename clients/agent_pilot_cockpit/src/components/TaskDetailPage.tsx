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

  const snapshot = task.snapshot;
  const taskView = snapshot.task;
  const actions: TaskAction[] = snapshot.actions;

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
        <p className="detail-summary">{taskView.summary || taskView.input_text || "Task detail is available once planning starts."}</p>
      </section>

      <PendingActionsPanel actions={actions} onAction={onAction} />

      <ArtifactPreviewPanel
        artifacts={snapshot.artifacts}
        selectedKind={selectedKind}
        onSelectKind={onSelectKind}
        preview={preview}
      />

      <ExecutionTimelinePanel
        steps={taskView.steps}
        toolExecutions={task.tool_executions}
        revisions={task.revisions}
      />
    </section>
  );
}
