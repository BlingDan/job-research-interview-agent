import type { TaskAction } from "../types";

interface PendingActionsPanelProps {
  actions: TaskAction[];
  onAction: (action: TaskAction) => void;
}

export function PendingActionsPanel({ actions, onAction }: PendingActionsPanelProps) {
  return (
    <section className="panel">
      <div className="panel-header">
        <div>
          <p className="eyebrow">Action Queue</p>
          <h3>Pending Actions</h3>
        </div>
      </div>
      {actions.length === 0 ? (
        <p className="empty-copy">No pending actions for the current task.</p>
      ) : (
        <div className="action-list">
          {actions.map((action) => (
            <button key={`${action.task_id}-${action.type}`} type="button" className="action-card" onClick={() => onAction(action)}>
              <strong>{action.label}</strong>
              <span>{action.description}</span>
            </button>
          ))}
        </div>
      )}
    </section>
  );
}
