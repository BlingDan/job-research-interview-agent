from app.core.config import Settings


def test_agent_pilot_config_defaults():
    settings = Settings()

    assert settings.lark_mode == "fake"
    assert settings.agent_pilot_default_chat_id is None
    assert settings.workspace_root == "workspace"

