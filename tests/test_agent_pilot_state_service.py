from app.schemas.agent_pilot import AgentPilotTask
from app.services.state_service import StateService


def test_save_and_load_task(tmp_path):
    service = StateService(tmp_path)
    task = AgentPilotTask(
        task_id="task-1",
        input_text="生成方案",
        chat_id="oc_demo",
    )

    service.save_task(task)
    loaded = service.load_task("task-1")

    assert loaded.task_id == "task-1"
    assert loaded.input_text == "生成方案"
    assert service.get_active_task_id("oc_demo") == "task-1"


def test_update_status_persists(tmp_path):
    service = StateService(tmp_path)
    task = AgentPilotTask(task_id="task-1", input_text="生成方案")

    service.update_status(task, "WAITING_CONFIRMATION")
    loaded = service.load_task("task-1")

    assert loaded.status == "WAITING_CONFIRMATION"

