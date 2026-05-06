from __future__ import annotations

import asyncio
from collections import defaultdict


class EventBus:
    _instance: EventBus | None = None

    def __init__(self) -> None:
        self._queues: dict[str, list[asyncio.Queue[dict]]] = defaultdict(list)
        self._loop: asyncio.AbstractEventLoop | None = None

    def set_loop(self, loop: asyncio.AbstractEventLoop) -> None:
        self._loop = loop

    def publish(self, task_id: str, event_type: str, data: dict | None = None) -> None:
        if self._loop is None:
            return
        event = {"task_id": task_id, "type": event_type, "data": data or {}}
        for q in self._queues.get(task_id, []):
            self._loop.call_soon_threadsafe(q.put_nowait, event)
        for q in self._queues.get("*", []):
            self._loop.call_soon_threadsafe(q.put_nowait, event)

    def subscribe(self, task_id: str) -> asyncio.Queue[dict]:
        q: asyncio.Queue[dict] = asyncio.Queue(maxsize=200)
        self._queues[task_id].append(q)
        return q

    def unsubscribe(self, task_id: str, q: asyncio.Queue[dict]) -> None:
        queues = self._queues.get(task_id, [])
        if q in queues:
            queues.remove(q)
        if not queues:
            self._queues.pop(task_id, None)

    @classmethod
    def get(cls) -> EventBus:
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance


event_bus = EventBus.get()
