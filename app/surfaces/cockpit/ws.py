from __future__ import annotations

import asyncio

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from app.shared.event_bus import event_bus
from app.shared.snapshots import build_surface_detail, summarize_task
from app.shared.state_service import DbStateService


router = APIRouter(tags=["cockpit-ws"])

_db_path = "workspace/agent_pilot.db"


def set_db_path(path: str) -> None:
    global _db_path
    _db_path = path


@router.websocket("/api/cockpit/ws/tasks/{task_id}")
async def ws_task(task_id: str, websocket: WebSocket) -> None:
    await websocket.accept()
    queue = event_bus.subscribe(task_id)
    try:
        state = DbStateService(_db_path)
        task = state.load_task_or_none(task_id)
        if task:
            await websocket.send_json(
                {
                    "type": "task_state",
                    "data": build_surface_detail(task, "cockpit"),
                }
            )
        while True:
            try:
                event = await asyncio.wait_for(queue.get(), timeout=30)
                latest = state.load_task_or_none(task_id)
                if latest is not None:
                    event["data"] = build_surface_detail(latest, "cockpit")
                await websocket.send_json(event)
            except asyncio.TimeoutError:
                await websocket.send_json({"type": "ping"})
    except WebSocketDisconnect:
        pass
    finally:
        event_bus.unsubscribe(task_id, queue)


@router.websocket("/api/cockpit/ws/tasks")
async def ws_task_list(websocket: WebSocket) -> None:
    await websocket.accept()
    queue = event_bus.subscribe("*")
    state = DbStateService(_db_path)
    try:
        tasks = state.list_tasks(limit=20)
        await websocket.send_json(
            {
                "type": "task_list",
                "data": [summarize_task(task) for task in tasks],
            }
        )
        while True:
            try:
                event = await asyncio.wait_for(queue.get(), timeout=30)
                event["data"] = [summarize_task(task) for task in state.list_tasks(limit=20)]
                await websocket.send_json(event)
            except asyncio.TimeoutError:
                await websocket.send_json({"type": "ping"})
    except WebSocketDisconnect:
        pass
    finally:
        event_bus.unsubscribe("*", queue)
