from fastapi import FastAPI
from app.api.routers.health import router as health_router
from app.api.routers.stream import router as stream_router
from app.api.routers.task import router as task_router

app = FastAPI(title="Job Research & Interview Prep Agent")

app.include_router(health_router)
app.include_router(stream_router)   
app.include_router(task_router)

