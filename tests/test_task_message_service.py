from app.services.task_message_service import TaskMessageService


def test_parse_confirm():
    command = TaskMessageService().parse_text("确认", chat_id="oc")

    assert command.type == "confirm"
    assert command.chat_id == "oc"


def test_parse_progress_query():
    command = TaskMessageService().parse_text("现在做到哪了？")

    assert command.type == "progress"


def test_parse_current_progress_query():
    command = TaskMessageService().parse_text("当前进度")

    assert command.type == "progress"


def test_parse_slash_status_command():
    command = TaskMessageService().parse_text("/status")

    assert command.type == "progress"


def test_parse_revision():
    command = TaskMessageService().parse_text("修改：PPT 更突出工程实现")

    assert command.type == "revise"


def test_parse_slash_help_command():
    command = TaskMessageService().parse_text("/help")

    assert command.type == "help"


def test_parse_slash_reset_command():
    command = TaskMessageService().parse_text("/reset")

    assert command.type == "reset"


def test_parse_new_task_strips_agent_mention():
    command = TaskMessageService().parse_text("@Agent 帮我生成参赛方案")

    assert command.type == "new_task"
    assert command.text == "帮我生成参赛方案"


def test_parse_ping_as_health_check():
    command = TaskMessageService().parse_text("ping", chat_id="oc_demo", message_id="om_demo")

    assert command.type == "health"
    assert command.chat_id == "oc_demo"
    assert command.message_id == "om_demo"


def test_parse_lark_raw_event_content():
    event = {
        "event": {
            "message": {
                "message_id": "om_demo",
                "chat_id": "oc_demo",
                "content": "{\"text\":\"确认\"}",
            },
            "sender": {"sender_id": {"open_id": "ou_demo"}},
        }
    }

    command = TaskMessageService().parse_lark_event(event)

    assert command.type == "confirm"
    assert command.chat_id == "oc_demo"
    assert command.message_id == "om_demo"
    assert command.user_id == "ou_demo"
