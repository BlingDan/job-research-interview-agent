import uuid
from fastapi import APIRouter
from app.schemas.task import TaskCreateRequest,TaskCreateResponse

# 创建一个路由组，打上标签 task
router = APIRouter(tags=["tasks"])

@router.post("/tasks", response_model=TaskCreateResponse) # 接口返回的函数要符合TaskCreateResponse的结构
def create_task(payload: TaskCreateRequest):    # 接收的请求体是 TaskCreateRequest
    # 生成唯一任务id
    task_id = str(uuid.uuid4())   
    
    return TaskCreateResponse(task_id =task_id, status="created")