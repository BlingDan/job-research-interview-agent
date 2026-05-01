from __future__ import annotations

import json
import time
import uuid
from pathlib import Path

from app.schemas.agent_pilot import AgentPilotStatus, AgentPilotTask, utc_now


class StateService:
    def __init__(self, workspace_root: str | Path = "workspace"):
        self.workspace_root = Path(workspace_root)
        self.tasks_root = self.workspace_root / "tasks"
        self.indexes_root = self.workspace_root / "indexes"
        self.chat_index_path = self.indexes_root / "chat_tasks.json"

    def task_dir(self, task_id: str) -> Path:
        return self.tasks_root / task_id

    def save_task(self, task: AgentPilotTask) -> AgentPilotTask:
        task.updated_at = utc_now()
        task_dir = self.task_dir(task.task_id)
        task_dir.mkdir(parents=True, exist_ok=True)
        _write_json_atomic(task_dir / "state.json", task.model_dump())
        if task.chat_id:
            self.bind_chat(task.chat_id, task.task_id)
        return task

    def load_task(self, task_id: str) -> AgentPilotTask:
        state_path = self.task_dir(task_id) / "state.json"
        data = json.loads(_read_text_with_retry(state_path))
        return AgentPilotTask.model_validate(data)

    def bind_chat(self, chat_id: str, task_id: str) -> None:
        index = self._read_chat_index()
        index[chat_id] = task_id
        self.indexes_root.mkdir(parents=True, exist_ok=True)
        _write_json_atomic(self.chat_index_path, index)

    def get_active_task_id(self, chat_id: str) -> str | None:
        return self._read_chat_index().get(chat_id)

    def clear_active_task(self, chat_id: str) -> None:
        index = self._read_chat_index()
        if chat_id not in index:
            return
        index.pop(chat_id)
        self.indexes_root.mkdir(parents=True, exist_ok=True)
        _write_json_atomic(self.chat_index_path, index)

    def update_status(
        self, task: AgentPilotTask, status: AgentPilotStatus
    ) -> AgentPilotTask:
        task.status = status
        return self.save_task(task)

    def _read_chat_index(self) -> dict[str, str]:
        if not self.chat_index_path.exists():
            return {}
        return json.loads(_read_text_with_retry(self.chat_index_path))


def _read_text_with_retry(path: Path) -> str:
    last_error: OSError | None = None
    for attempt in range(5):
        try:
            return path.read_text(encoding="utf-8")
        except PermissionError as exc:
            last_error = exc
            time.sleep(0.02 * (attempt + 1))
    if last_error:
        raise last_error
    return path.read_text(encoding="utf-8")


def _write_json_atomic(path: Path, data: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp_path = path.with_name(f"{path.name}.{uuid.uuid4().hex}.tmp")
    tmp_path.write_text(
        json.dumps(data, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    for attempt in range(5):
        try:
            tmp_path.replace(path)
            return
        except PermissionError:
            if attempt == 4:
                raise
            time.sleep(0.02 * (attempt + 1))
