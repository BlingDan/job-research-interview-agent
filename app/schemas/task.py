from pydantic import BaseModel


class TaskCreateRequest(BaseModel):
    jd_text: str
    company_name: str | None = None
    interview_topic: str | None = None
    local_context_path: str | None = None
    user_note: str | None = None


class TaskCreateResponse(BaseModel):
    task_id: str
    status: str