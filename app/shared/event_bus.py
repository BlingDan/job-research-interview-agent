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
        for queue in self._queues.get(task_id, []):
            self._loop.call_soon_threadsafe(queue.put_nowait, event)
        for queue in self._queues.get("*", []):
            self._loop.call_soon_threadsafe(queue.put_nowait, event)

    def subscribe(self, task_id: str) -> asyncio.Queue[dict]:
        queue: asyncio.Queue[dict] = asyncio.Queue(maxsize=200)
        self._queues[task_id].append(queue)
        return queue

    def unsubscribe(self, task_id: str, queue: asyncio.Queue[dict]) -> None:
        queues = self._queues.get(task_id, [])
        if queue in queues:
            queues.remove(queue)
        if not queues:
            self._queues.pop(task_id, None)

    @classmethod
    def get(cls) -> EventBus:
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance


event_bus = EventBus.get()

__all__ = ["EventBus", "event_bus"]
