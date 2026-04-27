from fastapi import FastAPI
from app.api.routers.health import router as health_router
from app.api.routers.stream import router as stream_router
from app.api.routers.task import router as task_router
from app.api.routers.upload import router as upload_router

app = FastAPI(title="Agent-Pilot")

app.include_router(health_router)
app.include_router(stream_router)   
app.include_router(task_router)
app.include_router(upload_router)

