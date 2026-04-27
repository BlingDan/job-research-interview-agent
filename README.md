<div align="center">
  <img src="./assets/img/agent-pilot.png" alt="Agent-Pilot hero image" width="100%" />
  <h1>Agent-Pilot</h1>
  <h3>基于 IM 的办公协同智能助手</h3>
  <p><em>从飞书/Lark IM 对话到文档、汇报材料与画板的一键智能闭环</em></p>
  <p>
    <img src="https://img.shields.io/github/stars/BlingDan/job-research-interview-agent?style=flat&logo=github" alt="GitHub stars" />
    <img src="https://img.shields.io/github/forks/BlingDan/job-research-interview-agent?style=flat&logo=github" alt="GitHub forks" />
    <img src="https://img.shields.io/badge/platform-Feishu%20%2F%20Lark-3370ff?style=flat" alt="Feishu/Lark platform" />
    <img src="https://img.shields.io/badge/language-Chinese-brightgreen?style=flat" alt="Language" />
    <img src="https://img.shields.io/badge/backend-FastAPI-009688?style=flat&logo=fastapi" alt="FastAPI" />
    <a href="https://github.com/BlingDan/job-research-interview-agent"><img src="https://img.shields.io/badge/GitHub-Project-blue?style=flat&logo=github" alt="GitHub Project" /></a>
  </p>
</div>

Agent-Pilot is a Feishu/Lark-native office collaboration Agent for the **基于 IM 的办公协同智能助手** competition track.

Agent-Pilot treats Feishu as the UI. Users start, confirm, query, revise, and receive final artifacts in Feishu IM. The backend acts as the Agent brain that plans work, generates Feishu office artifacts, and keeps task state consistent across desktop and mobile clients.

## Winning Demo Flow

```text
Feishu IM
-> Agent intent capture
-> Agent task plan
-> IM confirmation
-> Feishu Doc proposal
-> Feishu Slides deck
-> Feishu Canvas/Whiteboard architecture diagram
-> final IM delivery
-> progress query and revision in the same chat
```

Optimized demo input:

```text
@Agent 帮我基于飞书比赛赛题，生成一份参赛方案文档和 5 页答辩汇报材料。重点突出 Agent 编排、多端协同、飞书办公套件联动和工程实现。
```

## Competition Mapping

| Scenario | Requirement | Implementation |
| --- | --- | --- |
| A | Intent / instruction entry | Feishu IM messages become Agent-Pilot commands. |
| B | Task understanding and planning | `PlannerAgent` creates an executable plan and asks for `确认`. |
| C | Doc / whiteboard generation | `DocAgent` creates the proposal; `CanvasAgent` creates the architecture diagram. |
| D | Presentation generation | `PresentationAgent` creates a 5-page defense deck. |
| E | Multi-end collaboration | `chat_id` binds state and artifact links to the same Feishu chat. |
| F | Summary and delivery | `DeliveryService` sends final links and summary back to IM. |

## Current Architecture

```text
lark-cli event +subscribe
        |
        v
TaskMessageService
        |
        v
AgentPilotOrchestrator
        |
        +--> PlannerAgent
        |       |
        |       +--> ArtifactBrief + ToolPlan
        +--> DocAgent
        +--> PresentationAgent
        +--> CanvasAgent
        |
        v
FeishuToolLayer
        |
        +--> FeishuMcpToolAdapter
        +--> LarkCliToolAdapter
        +--> FakeArtifact fallback
```

The project uses a mixed integration strategy:

- `fake`: default mode for tests and local demos; writes local artifacts and returns realistic fake URLs.
- `dry_run`: builds real `lark-cli` commands with `--dry-run`.
- `real`: calls `lark-cli` without `--dry-run` when Feishu permissions are ready.
- `LARK_IM_MODE` and `LARK_ARTIFACT_MODE` can split IM from artifact behavior. This is the safest competition mode for real Bot verification.
- `FEISHU_TOOL_MODE=hybrid` routes Agent tool calls through MCP where supported, then `lark-cli`, then fake fallback.
- `FEISHU_MCP_MODE=off|dry_run|real` controls whether the MCP adapter participates. The default is `off` so the live demo keeps using the proven `lark-cli` bridge.
- `FEISHU_MCP_MODE=real` currently applies only to Doc creation through official MCP `docx.builtin.import`; Slides and Canvas stay on the proven `lark-cli` path.
- `AGENT_PILOT_AUTO_CONFIRM=true` turns on goal-driven one-message execution: after the plan is posted, the Agent immediately continues through Doc, Slides, Canvas, and final IM delivery.

`ArtifactBrief` is generated once per task and shared by Doc, Slides, and Canvas. This keeps the three deliverables aligned with the official A-F competition scenarios instead of letting each artifact tell a different story.

`ToolPlan` is the Agent-facing explanation of tool use. It records which Feishu capability each step needs, why it is user-visible, and which adapters can execute it:

```text
PlannerAgent
-> ToolPlan(create_doc, create_slides, create_canvas, deliver_im_summary)
-> FeishuToolLayer
-> MCP when available
-> lark-cli for stable live execution
-> fake artifact fallback when permission or coverage blocks the real call
```

## Quick Start

### Run tests

```bash
uv run pytest
```

### Start API

```bash
uv run uvicorn app.main:app --reload
```

### Create a fake Agent-Pilot task

PowerShell:

```powershell
$body = @{
  message = "@Agent 帮我基于飞书比赛赛题，生成一份参赛方案文档和 5 页答辩汇报材料。重点突出 Agent 编排、多端协同、飞书办公套件联动和工程实现。"
  chat_id = "oc_demo"
  message_id = "om_demo"
  user_id = "ou_demo"
} | ConvertTo-Json

$created = Invoke-RestMethod -Method Post -Uri http://127.0.0.1:8000/tasks -ContentType "application/json" -Body $body
$created
```

Confirm and generate artifacts:

```powershell
Invoke-RestMethod -Method Post -Uri "http://127.0.0.1:8000/tasks/$($created.task_id)/confirm"
```

Revise:

```powershell
$revision = @{ instruction = "修改：PPT 更突出工程实现和多端协同" } | ConvertTo-Json
Invoke-RestMethod -Method Post -Uri "http://127.0.0.1:8000/tasks/$($created.task_id)/revise" -ContentType "application/json" -Body $revision
```

Generated fake artifacts are written under:

```text
workspace/tasks/<task_id>/
  state.json
  doc.md
  slides.json
  canvas.mmd
```

## Feishu IM Listener

Preflight:

```bash
lark-cli doctor --offline
```

Recommended `.env` for the full competition demo:

```dotenv
LARK_IM_MODE=real
LARK_ARTIFACT_MODE=real
FEISHU_TOOL_MODE=hybrid
FEISHU_MCP_MODE=real
FEISHU_MCP_APP_ID=<your_app_id>
FEISHU_MCP_APP_SECRET=<your_app_secret>
FEISHU_MCP_TOOLS=docx.builtin.import,docx.v1.document.rawContent,docx.builtin.search
FEISHU_MCP_TOKEN_MODE=user_access_token
FEISHU_MCP_USE_UAT=true
AGENT_PILOT_PLANNER_MODE=auto
AGENT_PILOT_AUTO_CONFIRM=true
LARK_STREAM_DELAY_SECONDS=0.2
```

With `AGENT_PILOT_AUTO_CONFIRM=true`, the live demo needs only one user message. Set it to `false` when you want the stricter “plan -> reply 确认 -> execute” judging walkthrough.

Authorize real Feishu office artifacts before using `LARK_ARTIFACT_MODE=real`:

```powershell
lark-cli auth login --domain docs
lark-cli auth login --domain slides
```

`docs` authorization is required for real Doc creation and for creating the document that hosts the Canvas/Whiteboard block. `slides` authorization is required for real Slides creation. If these authorizations are missing, Agent-Pilot can still run through fallback artifact mode, but the final links will not be real Feishu office files.

Run local IM event bridge:

```bash
uv run python scripts/lark_event_listener.py
```

For real Feishu Bot replies while keeping Doc/Slides/Canvas stable in fake mode:

```powershell
$env:LARK_IM_MODE="real"
$env:LARK_ARTIFACT_MODE="fake"
$env:FEISHU_TOOL_MODE="hybrid"
$env:FEISHU_MCP_MODE="off"
$env:LARK_STREAM_DELAY_SECONDS="0.2"
uv run python scripts/lark_event_listener.py
```

To let concrete artifacts try the real Feishu office suite first, switch artifact mode to `real`:

```powershell
lark-cli auth login --domain docs
lark-cli auth login --domain slides

$env:LARK_IM_MODE="real"
$env:LARK_ARTIFACT_MODE="real"
$env:FEISHU_TOOL_MODE="hybrid"
$env:FEISHU_MCP_MODE="off"
$env:AGENT_PILOT_PLANNER_MODE="auto"
$env:LARK_STREAM_DELAY_SECONDS="0.2"
uv run python scripts/lark_event_listener.py
```

In this mode `DocAgent` calls `lark-cli docs +create`, `PresentationAgent` calls `lark-cli slides +create`, and `CanvasAgent` creates a document with a blank whiteboard block before calling `lark-cli whiteboard +update` with Mermaid. If one artifact hits authorization or scope errors, Agent-Pilot falls back only for that artifact and still delivers the task in IM.

To let Doc creation try official Feishu MCP first, finish the one-time OAuth setup and then enable MCP mode.

First, add OAuth redirect URLs in the Feishu developer console for your app:

```text
http://localhost:3000/callback
http://localhost:3000/callback?redirect_uri=http://localhost:3000/callback
```

The second URL covers the re-authorize link emitted by the current `@larksuiteoapi/lark-mcp` package. If Feishu shows error `20029`, the redirect URL whitelist is the first thing to check.

PowerShell does not automatically load `.env`. If your MCP app credentials are stored there, load them into the current shell before running `login`. If you do not use `.env`, set `FEISHU_MCP_APP_ID` and `FEISHU_MCP_APP_SECRET` in the shell manually first.

```powershell
Get-Content .env | ForEach-Object {
  if ($_ -match '^\s*([^#][^=]+?)\s*=\s*(.*)\s*$') {
    [Environment]::SetEnvironmentVariable($matches[1].Trim(), $matches[2].Trim().Trim('"'), 'Process')
  }
}
```

Then log in. Keep the scope in quotes so PowerShell does not split it into extra arguments:

```powershell
npx -y @larksuiteoapi/lark-mcp login `
  -a $env:FEISHU_MCP_APP_ID `
  -s $env:FEISHU_MCP_APP_SECRET `
  --scope "offline_access docx:document"

$env:LARK_IM_MODE="real"
$env:LARK_ARTIFACT_MODE="real"
$env:FEISHU_TOOL_MODE="hybrid"
$env:FEISHU_MCP_MODE="real"
$env:FEISHU_MCP_TOOLS="docx.builtin.import,docx.v1.document.rawContent,docx.builtin.search"
$env:FEISHU_MCP_TOKEN_MODE="user_access_token"
$env:FEISHU_MCP_USE_UAT="true"
$env:AGENT_PILOT_PLANNER_MODE="auto"
$env:AGENT_PILOT_AUTO_CONFIRM="true"
uv run python scripts/lark_event_listener.py
```

MCP Doc mode uses official `docx.builtin.import` to create a new document from generated content. It is not direct in-place editing of an existing Doc. If MCP startup, schema detection, authorization, or import fails, the Tool Layer records the MCP failure with secrets redacted and falls back to `lark-cli` or fake artifact delivery.

If MCP OAuth keeps expiring during rehearsal, either re-run:

```powershell
npx -y @larksuiteoapi/lark-mcp login `
  -a $env:FEISHU_MCP_APP_ID `
  -s $env:FEISHU_MCP_APP_SECRET `
  --scope "offline_access docx:document"
```

or switch MCP Doc import to app/tenant token mode:

```dotenv
FEISHU_MCP_TOKEN_MODE=tenant_access_token
FEISHU_MCP_USE_UAT=false
```

The tenant-token option avoids user OAuth expiry, while the existing `mcp -> lark-cli -> fake` fallback still protects the live demo if app-owned Doc creation is blocked by permissions.

The listener consumes `lark-cli event +subscribe --compact`, parses IM messages, and routes them into the same Agent-Pilot orchestrator used by `/tasks`.

When a new task arrives, the Bot immediately replies with a planning status card so users know the Agent is working before the LLM finishes. Plan replies are then streamed by updating that same interactive Bot card with `PATCH /open-apis/im/v1/messages/{message_id}`. If Feishu returns a permission error, enable the Bot message update permission in the developer console; the code falls back to sending the final plan as a normal text reply.

Useful IM commands:

```text
/help
/status
/reset
确认
当前进度
修改：PPT 更突出工程实现和多端协同
```

`/reset` clears the task bound to the current chat without deleting historical artifacts, which is useful for repeated competition demos.

## Important Commands

```bash
uv run uvicorn app.main:app --reload
uv run pytest
uv run python scripts/lark_event_listener.py

lark-cli --help
lark-cli im --help
lark-cli docs --help
lark-cli slides --help
lark-cli whiteboard --help
lark-cli event +subscribe --help
```

## Notes

- Feishu is the UI. Do not build a custom dashboard or mobile/desktop client.
- Fake/dry-run mode is intentional and keeps demos reliable when Doc, Slides, or Whiteboard permissions are blocked.
- The old job-research workflow remains in some legacy modules for now, but `/tasks` is now Agent-Pilot.
