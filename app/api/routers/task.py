import uuid
from fastapi import APIRouter
from app.schemas.task import TaskCreateRequest,TaskCreateResponse
from app.services.orchestration_service import run_research


# 创建一个路由组，打上标签 task
router = APIRouter(tags=["tasks"])

@router.post("/tasks", response_model=TaskCreateResponse) # 接口返回的函数要符合TaskCreateResponse的结构
# 接收的请求体是 TaskCreateRequest的结构
def create_task(payload: TaskCreateRequest):    
    # 生成唯一任务id
    task_id = str(uuid.uuid4())   
    
    
    return run_research(task_id, payload)