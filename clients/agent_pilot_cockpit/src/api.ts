import type { ArtifactPreview, TaskDetail, TaskSummary } from "./types";

const JSON_HEADERS = { "Content-Type": "application/json" };

async function getJson<T>(path: string): Promise<T> {
  const response = await fetch(path);
  if (!response.ok) {
    throw new Error(`Request failed: ${response.status}`);
  }
  return response.json() as Promise<T>;
}

async function postJson<T>(path: string, body?: unknown): Promise<T> {
  const response = await fetch(path, {
    method: "POST",
    headers: JSON_HEADERS,
    body: body === undefined ? undefined : JSON.stringify(body),
  });
  if (!response.ok) {
    throw new Error(`Request failed: ${response.status}`);
  }
  return response.json() as Promise<T>;
}

export async function listTasks(): Promise<TaskSummary[]> {
  const payload = await getJson<{ tasks: TaskSummary[] }>("/api/cockpit/tasks");
  return payload.tasks;
}

export function getTask(taskId: string): Promise<TaskDetail> {
  return getJson<TaskDetail>(`/api/cockpit/tasks/${taskId}`);
}

export function getArtifact(taskId: string, kind: string): Promise<ArtifactPreview> {
  return getJson<ArtifactPreview>(`/api/cockpit/tasks/${taskId}/artifacts/${kind}`);
}

export function createCommand(message: string): Promise<TaskDetail> {
  return postJson<TaskDetail>("/api/im/commands", {
    message,
    chat_id: "cockpit_demo",
    message_id: `cockpit_${Date.now()}`,
  });
}

export function confirmTask(taskId: string): Promise<TaskDetail> {
  return postJson<TaskDetail>(`/api/assistant/tasks/${taskId}/actions/confirm`);
}

export function resetTask(taskId: string): Promise<TaskDetail> {
  return postJson<TaskDetail>(`/api/assistant/tasks/${taskId}/actions/reset`);
}

export function reviseTask(taskId: string, instruction: string): Promise<TaskDetail> {
  return postJson<TaskDetail>(`/api/assistant/tasks/${taskId}/actions/revise`, {
    instruction,
  });
}

export function openTaskSocket(taskId: string): WebSocket {
  const protocol = window.location.protocol === "https:" ? "wss" : "ws";
  return new WebSocket(`${protocol}://${window.location.host}/api/cockpit/ws/tasks/${taskId}`);
}
