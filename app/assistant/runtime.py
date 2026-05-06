from __future__ import annotations

from app.assistant.orchestrator import AgentPilotOrchestrator
from app.core.config import get_settings
from app.integrations.artifacts import (
    ArtifactFallbackLarkClient,
    FeishuMcpToolAdapter,
    FeishuToolLayer,
    LarkCliToolAdapter,
)
from app.integrations.feishu import (
    FakeLarkClient,
    HybridLarkClient,
    LarkCliClient,
    LarkClient,
    SubprocessFeishuMcpClient,
)
from app.shared.state_service import DbStateService


def build_orchestrator(
    *, background_auto_confirm: bool | None = None
) -> AgentPilotOrchestrator:
    settings = get_settings()
    state_service = DbStateService(settings.workspace_root + "/agent_pilot.db")
    im_mode = settings.lark_im_mode or settings.lark_mode
    artifact_mode = settings.lark_artifact_mode or settings.lark_mode
    im_client = _build_lark_client(im_mode, settings.lark_cli_timeout_seconds)
    artifact_client = _build_lark_client(
        artifact_mode, settings.lark_cli_timeout_seconds
    )
    if artifact_mode == "real":
        artifact_client = ArtifactFallbackLarkClient(
            primary=artifact_client,
            fallback=FakeLarkClient(),
        )
    if im_mode == artifact_mode and artifact_mode != "real":
        lark_client = im_client
    else:
        lark_client = HybridLarkClient(
            im_client=im_client,
            artifact_client=artifact_client,
        )
    return AgentPilotOrchestrator(
        state_service,
        lark_client,
        stream_delay_seconds=getattr(settings, "lark_stream_delay_seconds", 0.0),
        auto_confirm=getattr(settings, "agent_pilot_auto_confirm", False),
        background_auto_confirm=(
            getattr(settings, "agent_pilot_background_auto_confirm", False)
            if background_auto_confirm is None
            else background_auto_confirm
        ),
        tool_layer=_build_tool_layer(
            getattr(settings, "feishu_tool_mode", "hybrid"),
            getattr(settings, "feishu_mcp_mode", "off"),
            getattr(settings, "feishu_mcp_app_id", ""),
            getattr(settings, "feishu_mcp_app_secret", ""),
            getattr(settings, "feishu_mcp_domain", "https://open.feishu.cn"),
            getattr(
                settings,
                "feishu_mcp_tools",
                "docx.builtin.import,docx.v1.document.rawContent,docx.builtin.search",
            ),
            getattr(settings, "feishu_mcp_timeout_seconds", 20.0),
            getattr(settings, "feishu_mcp_token_mode", "user_access_token"),
            getattr(settings, "feishu_mcp_use_uat", True),
            getattr(settings, "feishu_tool_adapter_timeout_seconds", 25.0),
            lark_client,
        ),
    )


def _build_lark_client(mode: str, timeout_seconds: float) -> LarkClient:
    if mode == "real":
        return LarkCliClient(dry_run=False, timeout_seconds=timeout_seconds)
    if mode == "dry_run":
        return LarkCliClient(dry_run=True, timeout_seconds=timeout_seconds)
    return FakeLarkClient()


def _build_tool_layer(
    tool_mode: str,
    mcp_mode: str,
    mcp_app_id: str,
    mcp_app_secret: str,
    mcp_domain: str,
    mcp_tools: str,
    mcp_timeout_seconds: float,
    mcp_token_mode: str,
    mcp_use_uat: bool,
    adapter_timeout_seconds: float,
    lark_client: LarkClient,
) -> FeishuToolLayer:
    mcp_client = None
    if mcp_mode != "off" and mcp_app_id and mcp_app_secret:
        mcp_client = SubprocessFeishuMcpClient(
            app_id=mcp_app_id,
            app_secret=mcp_app_secret,
            domain=mcp_domain,
            tools=_split_csv(mcp_tools),
            timeout_seconds=mcp_timeout_seconds,
            token_mode=(
                mcp_token_mode
                if mcp_token_mode
                in {"auto", "user_access_token", "tenant_access_token"}
                else "user_access_token"
            ),
        )
    mcp_adapter = FeishuMcpToolAdapter(
        mode=mcp_mode if mcp_mode in {"off", "dry_run", "real"} else "off",
        client=mcp_client,
        secrets=[mcp_app_secret],
        use_uat=mcp_use_uat,
    )
    lark_adapter = LarkCliToolAdapter(lark_client)
    fake_adapter = LarkCliToolAdapter(FakeLarkClient())

    if tool_mode == "mcp":
        return FeishuToolLayer(
            {"mcp": mcp_adapter, "fake": fake_adapter},
            adapter_timeout_seconds=adapter_timeout_seconds,
        )
    if tool_mode == "lark_cli":
        return FeishuToolLayer(
            {"lark_cli": lark_adapter, "fake": fake_adapter},
            adapter_timeout_seconds=adapter_timeout_seconds,
        )
    if tool_mode == "fake":
        return FeishuToolLayer(
            {"fake": fake_adapter},
            adapter_timeout_seconds=adapter_timeout_seconds,
        )
    return FeishuToolLayer(
        {
            "mcp": mcp_adapter,
            "lark_cli": lark_adapter,
            "fake": fake_adapter,
        },
        adapter_timeout_seconds=adapter_timeout_seconds,
    )


def _split_csv(value: str) -> list[str]:
    return [item.strip() for item in value.split(",") if item.strip()]
