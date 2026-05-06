import type { TaskSummary } from "../types";

interface TaskListPageProps {
  tasks: TaskSummary[];
  selectedTaskId: string | null;
  onSelect: (taskId: string) => void;
}

export function TaskListPage({ tasks, selectedTaskId, onSelect }: TaskListPageProps) {
  return (
    <section className="panel task-list-panel">
      <div className="panel-header">
        <div>
          <p className="eyebrow">Cockpit</p>
          <h2>Task Overview</h2>
        </div>
        <span className="badge">{tasks.length} tasks</span>
      </div>
      <div className="task-list">
        {tasks.map((task) => (
          <button
            key={task.task_id}
            className={`task-card ${selectedTaskId === task.task_id ? "selected" : ""}`}
            onClick={() => onSelect(task.task_id)}
            type="button"
          >
            <div className="task-card-top">
              <strong>{task.status}</strong>
              <span>{new Date(task.updated_at).toLocaleString()}</span>
            </div>
            <p>{task.input_text}</p>
            <small>{task.summary || "No summary yet."}</small>
          </button>
        ))}
      </div>
    </section>
  );
}
