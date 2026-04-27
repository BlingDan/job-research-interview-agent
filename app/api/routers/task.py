from fastapi import APIRouter, HTTPException

from app.core.config import get_settings
from app.integrations.artifact_fallback_lark_client import ArtifactFallbackLarkClient
from app.integrations.fake_lark_client import FakeLarkClient
from app.integrations.feishu_mcp_client import SubprocessFeishuMcpClient
from app.integrations.hybrid_lark_client import HybridLarkClient
from app.integrations.lark_cli_client import LarkCliClient
from app.integrations.lark_client import LarkClient
from app.schemas.agent_pilot import (
    AgentPilotResponse,
    TaskActionRequest,
    TaskCreateRequest,
)
from app.services.feishu_tool_layer import FeishuMcpToolAdapter, FeishuToolLayer, LarkCliToolAdapter
from app.services.orchestrator import AgentPilotOrchestrator
from app.services.state_service import StateService


router = APIRouter(tags=["tasks"])


def build_orchestrator() -> AgentPilotOrchestrator:
    settings = get_settings()
    state_service = StateService(settings.workspace_root)
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
            token_mode=mcp_token_mode if mcp_token_mode in {"auto", "user_access_token", "tenant_access_token"} else "user_access_token",
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
        return FeishuToolLayer({"mcp": mcp_adapter, "fake": fake_adapter})
    if tool_mode == "lark_cli":
        return FeishuToolLayer({"lark_cli": lark_adapter, "fake": fake_adapter})
    if tool_mode == "fake":
        return FeishuToolLayer({"fake": fake_adapter})
    return FeishuToolLayer(
        {
            "mcp": mcp_adapter,
            "lark_cli": lark_adapter,
            "fake": fake_adapter,
        }
    )


def _split_csv(value: str) -> list[str]:
    return [item.strip() for item in value.split(",") if item.strip()]


@router.post("/tasks", response_model=AgentPilotResponse)
def create_task(payload: TaskCreateRequest):
    return build_orchestrator().create_task(payload)


@router.post("/tasks/{task_id}/confirm", response_model=AgentPilotResponse)
def confirm_task(task_id: str):
    try:
        return build_orchestrator().confirm_task(task_id)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail="task not found") from exc


@router.post("/tasks/{task_id}/revise", response_model=AgentPilotResponse)
def revise_task(task_id: str, payload: TaskActionRequest):
    instruction = payload.instruction or payload.message or ""
    if not instruction.strip():
        raise HTTPException(status_code=400, detail="revision instruction is required")
    try:
        return build_orchestrator().revise_task(task_id, instruction)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail="task not found") from exc


@router.get("/tasks/{task_id}", response_model=AgentPilotResponse)
def get_task(task_id: str):
    try:
        return build_orchestrator().get_task(task_id)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail="task not found") from exc
