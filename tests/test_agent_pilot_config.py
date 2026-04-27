from app.core.config import Settings


def test_agent_pilot_config_defaults():
    settings = Settings(_env_file=None)

    assert settings.lark_mode == "fake"
    assert settings.lark_im_mode is None
    assert settings.lark_artifact_mode is None
    assert settings.lark_stream_delay_seconds == 0.0
    assert settings.agent_pilot_default_chat_id is None
    assert settings.agent_pilot_auto_confirm is False
    assert settings.agent_pilot_planner_mode == "fallback"
    assert settings.feishu_tool_mode == "hybrid"
    assert settings.feishu_mcp_mode == "off"
    assert settings.feishu_mcp_app_id == ""
    assert settings.feishu_mcp_app_secret == ""
    assert settings.feishu_mcp_domain == "https://open.feishu.cn"
    assert "docx.builtin.import" in settings.feishu_mcp_tools
    assert settings.feishu_mcp_timeout_seconds == 20.0
    assert settings.feishu_mcp_token_mode == "user_access_token"
    assert settings.feishu_mcp_use_uat is True
    assert settings.workspace_root == "workspace"


def test_agent_pilot_config_reads_feishu_mcp_env(monkeypatch):
    monkeypatch.setenv("FEISHU_MCP_APP_ID", "cli_demo")
    monkeypatch.setenv("FEISHU_MCP_APP_SECRET", "secret-value")
    monkeypatch.setenv("FEISHU_MCP_MODE", "real")
    monkeypatch.setenv("FEISHU_MCP_TIMEOUT_SECONDS", "9")
    monkeypatch.setenv("FEISHU_MCP_TOKEN_MODE", "tenant_access_token")
    monkeypatch.setenv("FEISHU_MCP_USE_UAT", "false")

    settings = Settings(_env_file=None)

    assert settings.feishu_mcp_app_id == "cli_demo"
    assert settings.feishu_mcp_app_secret == "secret-value"
    assert settings.feishu_mcp_mode == "real"
    assert settings.feishu_mcp_timeout_seconds == 9.0
    assert settings.feishu_mcp_token_mode == "tenant_access_token"
    assert settings.feishu_mcp_use_uat is False


def test_agent_pilot_config_reads_auto_confirm_env(monkeypatch):
    monkeypatch.setenv("AGENT_PILOT_AUTO_CONFIRM", "true")

    settings = Settings(_env_file=None)

    assert settings.agent_pilot_auto_confirm is True
