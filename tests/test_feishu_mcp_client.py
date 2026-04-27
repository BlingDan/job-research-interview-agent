from app.integrations.feishu_mcp_client import SubprocessFeishuMcpClient, sanitize_text


def test_subprocess_mcp_client_builds_official_command_and_redacts_secret():
    client = SubprocessFeishuMcpClient(
        app_id="cli_demo",
        app_secret="secret-value",
        domain="https://open.feishu.cn",
        tools=["docx.builtin.import", "docx.builtin.search"],
        timeout_seconds=7,
    )

    command, args = client.build_command()
    safe_command = client.safe_command_for_log()

    assert command == "npx"
    assert args[:4] == ["-y", "@larksuiteoapi/lark-mcp", "mcp", "-a"]
    assert "cli_demo" in args
    assert "secret-value" in args
    assert "--oauth" in args
    assert "-t" in args
    assert "docx.builtin.import,docx.builtin.search" in args
    assert "secret-value" not in safe_command
    assert "***" in safe_command


def test_subprocess_mcp_client_can_use_tenant_token_mode_without_oauth():
    client = SubprocessFeishuMcpClient(
        app_id="cli_demo",
        app_secret="secret-value",
        tools=["docx.builtin.import"],
        token_mode="tenant_access_token",
    )

    _, args = client.build_command()

    assert "--token-mode" in args
    assert args[args.index("--token-mode") + 1] == "tenant_access_token"
    assert "--oauth" not in args


def test_sanitize_text_removes_known_secret_and_token_like_values():
    text = "permission denied for secret-value with bearer abc.def.ghi and user_access_token=uut-123"

    sanitized = sanitize_text(text, secrets=["secret-value"])

    assert "secret-value" not in sanitized
    assert "abc.def.ghi" not in sanitized
    assert "uut-123" not in sanitized
