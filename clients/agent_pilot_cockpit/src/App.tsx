import { useEffect, useState } from "react";
import {
  confirmTask,
  createCommand,
  getArtifact,
  getTask,
  listTasks,
  openTaskSocket,
  resetTask,
  reviseTask,
} from "./api";
import { TaskDetailPage } from "./components/TaskDetailPage";
import { TaskListPage } from "./components/TaskListPage";
import type { ArtifactPreview, TaskAction, TaskDetail, TaskSummary } from "./types";

export default function App() {
  const [tasks, setTasks] = useState<TaskSummary[]>([]);
  const [selectedTaskId, setSelectedTaskId] = useState<string | null>(null);
  const [taskDetail, setTaskDetail] = useState<TaskDetail | null>(null);
  const [artifactPreview, setArtifactPreview] = useState<ArtifactPreview | null>(null);
  const [selectedKind, setSelectedKind] = useState<"doc" | "slides" | "canvas" | null>(null);
  const [quickCommand, setQuickCommand] = useState("Create an office collaboration package with doc, slides, and canvas");
  const [error, setError] = useState<string | null>(null);

  async function refreshTasks(preserveSelection = true) {
    try {
      const nextTasks = await listTasks();
      setTasks(nextTasks);
      if (!preserveSelection || !selectedTaskId) {
        setSelectedTaskId(nextTasks[0]?.task_id ?? null);
      }
    } catch (nextError) {
      setError(nextError instanceof Error ? nextError.message : "Failed to load tasks.");
    }
  }

  useEffect(() => {
    void refreshTasks(false);
  }, []);

  useEffect(() => {
    if (!selectedTaskId) {
      setTaskDetail(null);
      setArtifactPreview(null);
      return;
    }

    let active = true;
    getTask(selectedTaskId)
      .then((detail) => {
        if (!active) {
          return;
        }
        setTaskDetail(detail);
        const firstKind = detail.snapshot.artifacts[0]?.kind ?? null;
        setSelectedKind((current) => current ?? firstKind);
      })
      .catch((nextError) => {
        if (!active) {
          return;
        }
        setError(nextError instanceof Error ? nextError.message : "Failed to load task.");
      });

    const socket = openTaskSocket(selectedTaskId);
    socket.onmessage = () => {
      void refreshTasks();
      void getTask(selectedTaskId).then((detail) => {
        if (active) {
          setTaskDetail(detail);
        }
      });
    };
    socket.onerror = () => {
      setError("Cockpit websocket disconnected.");
    };

    return () => {
      active = false;
      socket.close();
    };
  }, [selectedTaskId]);

  useEffect(() => {
    if (!selectedTaskId || !selectedKind) {
      setArtifactPreview(null);
      return;
    }

    let active = true;
    getArtifact(selectedTaskId, selectedKind)
      .then((preview) => {
        if (active) {
          setArtifactPreview(preview);
        }
      })
      .catch(() => {
        if (active) {
          setArtifactPreview(null);
        }
      });
    return () => {
      active = false;
    };
  }, [selectedKind, selectedTaskId, taskDetail]);

  async function handleAction(action: TaskAction) {
    if (!taskDetail) {
      return;
    }
    try {
      let nextDetail: TaskDetail;
      if (action.type === "confirm" || action.type === "retry") {
        nextDetail = await confirmTask(taskDetail.task_id);
      } else if (action.type === "reset") {
        nextDetail = await resetTask(taskDetail.task_id);
      } else {
        const instruction = window.prompt(
          "Revision instruction",
          "Revise slides to emphasize engineering implementation and cross-device sync",
        );
        if (!instruction) {
          return;
        }
        nextDetail = await reviseTask(taskDetail.task_id, instruction);
      }
      setTaskDetail(nextDetail);
      await refreshTasks();
    } catch (nextError) {
      setError(nextError instanceof Error ? nextError.message : "Action failed.");
    }
  }

  async function handleCreateCommand() {
    try {
      const detail = await createCommand(quickCommand);
      setSelectedTaskId(detail.task_id);
      setTaskDetail(detail);
      await refreshTasks();
    } catch (nextError) {
      setError(nextError instanceof Error ? nextError.message : "Failed to create task.");
    }
  }

  return (
    <div className="app-shell">
      <header className="hero-panel">
        <div>
          <p className="eyebrow">Agent-Pilot</p>
          <h1>Internal Cockpit</h1>
          <p className="hero-copy">
            Observe the same unified assistant task flowing across IM, cockpit, Windows, and Android surfaces.
          </p>
        </div>
        <div className="hero-actions">
          <textarea value={quickCommand} onChange={(event) => setQuickCommand(event.target.value)} rows={3} />
          <button type="button" onClick={handleCreateCommand}>
            Inject IM command
          </button>
        </div>
      </header>

      {error ? <div className="error-banner">{error}</div> : null}

      <main className="content-grid">
        <TaskListPage tasks={tasks} selectedTaskId={selectedTaskId} onSelect={setSelectedTaskId} />
        <TaskDetailPage
          task={taskDetail}
          preview={artifactPreview}
          selectedKind={selectedKind}
          onSelectKind={setSelectedKind}
          onAction={handleAction}
        />
      </main>
    </div>
  );
}
