import asyncio
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from app.api.routers.health import router as health_router
from app.core.config import get_settings
from app.shared.event_bus import event_bus
from app.surfaces.assistant.router import router as assistant_router
from app.surfaces.cockpit.router import router as cockpit_router
from app.surfaces.cockpit.ws import router as cockpit_ws_router, set_db_path
from app.surfaces.im.router import router as im_router
from app.surfaces.mobile.router import router as mobile_router
from app.surfaces.windows.router import router as windows_router

app = FastAPI(title="Agent-Pilot")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(health_router)
app.include_router(im_router)
app.include_router(assistant_router)
app.include_router(cockpit_router)
app.include_router(cockpit_ws_router)
app.include_router(windows_router)
app.include_router(mobile_router)

project_root = Path(__file__).resolve().parents[1]
legacy_static_dir = Path(__file__).parent / "static"
legacy_static_dir.mkdir(parents=True, exist_ok=True)
cockpit_dist_dir = project_root / "clients" / "agent_pilot_cockpit" / "dist"
served_static_dir = cockpit_dist_dir if cockpit_dist_dir.exists() else legacy_static_dir
app.mount("/static", StaticFiles(directory=str(served_static_dir)), name="static")


@app.on_event("startup")
async def startup() -> None:
    settings = get_settings()
    set_db_path(settings.workspace_root + "/agent_pilot.db")
    loop = asyncio.get_running_loop()
    event_bus.set_loop(loop)


@app.get("/")
async def root():
    from fastapi.responses import FileResponse

    if (served_static_dir / "index.html").exists():
        return FileResponse(str(served_static_dir / "index.html"))
    return {
        "name": "Agent-Pilot",
        "cockpit": "/static",
        "im_commands": "/api/im/commands",
    }
