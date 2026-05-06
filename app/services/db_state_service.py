from __future__ import annotations

import json
import sqlite3
import threading
from pathlib import Path

from app.schemas.agent_pilot import AgentPilotStatus, AgentPilotTask, utc_now
from app.services.event_bus import event_bus


class DbStateService:
    def __init__(self, db_path: str | Path = "workspace/agent_pilot.db"):
        raw = Path(db_path)
        if raw.is_dir() or raw.suffix == "":
            raw = raw / "agent_pilot.db"
        elif raw.suffix != ".db":
            raw = raw.parent / f"{raw.name}.db"
        self.db_path = raw
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._local = threading.local()
        self._init_db()

    def _get_conn(self) -> sqlite3.Connection:
        if not hasattr(self._local, "conn") or self._local.conn is None:
            conn = sqlite3.connect(str(self.db_path), check_same_thread=False)
            conn.row_factory = sqlite3.Row
            conn.execute("PRAGMA journal_mode=WAL")
            conn.execute("PRAGMA busy_timeout=5000")
            self._local.conn = conn
        return self._local.conn

    def _init_db(self) -> None:
        conn = sqlite3.connect(str(self.db_path))
        conn.execute("PRAGMA journal_mode=WAL")
        conn.executescript("""
            CREATE TABLE IF NOT EXISTS tasks (
                task_id TEXT PRIMARY KEY,
                chat_id TEXT,
                user_id TEXT,
                status TEXT NOT NULL DEFAULT 'CREATED',
                data_json TEXT NOT NULL,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            );
            CREATE INDEX IF NOT EXISTS idx_tasks_chat_id ON tasks(chat_id);
            CREATE INDEX IF NOT EXISTS idx_tasks_status ON tasks(status);
            CREATE INDEX IF NOT EXISTS idx_tasks_created ON tasks(created_at);

            CREATE TABLE IF NOT EXISTS chat_index (
                chat_id TEXT PRIMARY KEY,
                task_id TEXT NOT NULL
            );
        """)
        conn.commit()
        conn.close()

    def close(self) -> None:
        if hasattr(self._local, "conn") and self._local.conn is not None:
            try:
                self._local.conn.close()
            except Exception:
                pass
            self._local.conn = None

    def __enter__(self) -> DbStateService:
        return self

    def __exit__(self, *args: object) -> None:
        self.close()

    def save_task(self, task: AgentPilotTask) -> AgentPilotTask:
        task.updated_at = utc_now()
        conn = self._get_conn()
        conn.execute(
            """INSERT OR REPLACE INTO tasks (task_id, chat_id, user_id, status, data_json, created_at, updated_at)
               VALUES (?, ?, ?, ?, ?, ?, ?)""",
            (
                task.task_id,
                task.chat_id,
                task.user_id,
                task.status,
                task.model_dump_json(),
                task.created_at,
                task.updated_at,
            ),
        )
        conn.commit()
        if task.chat_id:
            self.bind_chat(task.chat_id, task.task_id)
        self._notify(task.task_id, "task_updated")
        return task

    def load_task(self, task_id: str) -> AgentPilotTask:
        conn = self._get_conn()
        row = conn.execute(
            "SELECT data_json FROM tasks WHERE task_id = ?", (task_id,)
        ).fetchone()
        if row is None:
            raise FileNotFoundError(f"task {task_id} not found")
        return AgentPilotTask.model_validate(json.loads(row["data_json"]))

    def load_task_or_none(self, task_id: str) -> AgentPilotTask | None:
        try:
            return self.load_task(task_id)
        except FileNotFoundError:
            return None

    def bind_chat(self, chat_id: str, task_id: str) -> None:
        conn = self._get_conn()
        conn.execute(
            "INSERT OR REPLACE INTO chat_index (chat_id, task_id) VALUES (?, ?)",
            (chat_id, task_id),
        )
        conn.commit()

    def get_active_task_id(self, chat_id: str) -> str | None:
        conn = self._get_conn()
        row = conn.execute(
            "SELECT task_id FROM chat_index WHERE chat_id = ?", (chat_id,)
        ).fetchone()
        return row["task_id"] if row else None

    def clear_active_task(self, chat_id: str) -> None:
        conn = self._get_conn()
        conn.execute("DELETE FROM chat_index WHERE chat_id = ?", (chat_id,))
        conn.commit()

    def task_dir(self, task_id: str) -> Path:
        p = self.db_path.parent / "task_files" / task_id
        p.mkdir(parents=True, exist_ok=True)
        return p

    def update_status(
        self, task: AgentPilotTask, status: AgentPilotStatus
    ) -> AgentPilotTask:
        task.status = status
        return self.save_task(task)

    def list_tasks(
        self, limit: int = 50, status: str | None = None
    ) -> list[AgentPilotTask]:
        conn = self._get_conn()
        if status:
            rows = conn.execute(
                "SELECT data_json FROM tasks WHERE status = ? ORDER BY created_at DESC LIMIT ?",
                (status, limit),
            ).fetchall()
        else:
            rows = conn.execute(
                "SELECT data_json FROM tasks ORDER BY created_at DESC LIMIT ?",
                (limit,),
            ).fetchall()
        return [AgentPilotTask.model_validate(json.loads(r["data_json"])) for r in rows]

    def _notify(self, task_id: str, event_type: str) -> None:
        try:
            event_bus.publish(task_id, event_type)
        except Exception:
            pass


class StateService(DbStateService):
    """Backwards-compatible alias that replaces the file-based StateService."""
