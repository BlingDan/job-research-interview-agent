# Agent-Pilot Demo Guide

This guide is optimized for the Feishu/Lark competition demo.

## 1. Preflight

Check local runtime:

```bash
uv run pytest
```

Check Feishu CLI status:

```bash
lark-cli doctor --offline
```

If user authorization is missing, keep artifact generation fake:

```powershell
$env:LARK_IM_MODE="real"
$env:LARK_ARTIFACT_MODE="fake"
```

## 2. Start API

```bash
uv run uvicorn app.main:app --reload
```

## 3. Fake API Demo

Create task:

```powershell
$body = @{
  message = "@Agent 帮我基于飞书比赛赛题，生成一份参赛方案文档和 5 页答辩汇报材料。重点突出 Agent 编排、多端协同、飞书办公套件联动和工程实现。"
  chat_id = "oc_demo"
  message_id = "om_demo"
  user_id = "ou_demo"
} | ConvertTo-Json

$created = Invoke-RestMethod -Method Post -Uri http://127.0.0.1:8000/tasks -ContentType "application/json" -Body $body
```

Expected:

```text
status: WAITING_CONFIRMATION
reply: plan + "回复「确认」..."
```

Confirm:

```powershell
$confirmed = Invoke-RestMethod -Method Post -Uri "http://127.0.0.1:8000/tasks/$($created.task_id)/confirm"
```

Expected:

```text
status: DONE
artifacts: doc, slides, canvas
```

Progress:

```powershell
Invoke-RestMethod -Method Get -Uri "http://127.0.0.1:8000/tasks/$($created.task_id)"
```

Revise:

```powershell
$revision = @{ instruction = "修改：PPT 更突出工程实现和多端协同" } | ConvertTo-Json
Invoke-RestMethod -Method Post -Uri "http://127.0.0.1:8000/tasks/$($created.task_id)/revise" -ContentType "application/json" -Body $revision
```

## 4. Real IM Listener Demo

Run:

```bash
uv run python scripts/lark_event_listener.py
```

Recommended stable competition mode:

```powershell
$env:LARK_IM_MODE="real"
$env:LARK_ARTIFACT_MODE="fake"
$env:FEISHU_TOOL_MODE="hybrid"
$env:FEISHU_MCP_MODE="off"
$env:AGENT_PILOT_PLANNER_MODE="auto"
$env:AGENT_PILOT_ROUTER_MODE="auto"
$env:LARK_STREAM_DELAY_SECONDS="0.2"
uv run python scripts/lark_event_listener.py
```

Real artifact mode:

```powershell
$env:LARK_IM_MODE="real"
$env:LARK_ARTIFACT_MODE="real"
$env:FEISHU_TOOL_MODE="hybrid"
$env:FEISHU_MCP_MODE="off"
$env:AGENT_PILOT_PLANNER_MODE="auto"
$env:AGENT_PILOT_ROUTER_MODE="auto"
$env:LARK_STREAM_DELAY_SECONDS="0.2"
uv run python scripts/lark_event_listener.py
```

This tries real Feishu Doc, Slides, and Whiteboard creation through `lark-cli` first. If a specific artifact lacks user authorization or app scopes, only that artifact falls back to local/fake metadata so the live IM demo can continue.

For the MCP Tool Layer story, keep `FEISHU_TOOL_MODE=hybrid`: Planner Agent now creates an internal `ToolPlan`, the orchestrator records execution through `FeishuToolLayer`, and the default route is MCP adapter detection -> `lark-cli` execution -> fake fallback. Keep `FEISHU_MCP_MODE=off` for the safest live run until a real MCP client is configured.

Official MCP Doc import mode:

Before logging in, add these OAuth redirect URLs in the Feishu developer console:

```text
http://localhost:3000/callback
http://localhost:3000/callback?redirect_uri=http://localhost:3000/callback
```

The second URL handles the current MCP package's re-authorize callback. If the browser shows Feishu error `20029`, update the redirect whitelist, save or publish the app settings, and run `login` again instead of refreshing the old page.

PowerShell does not read `.env` automatically. Load local MCP credentials before starting the OAuth flow. If you do not use `.env`, set `FEISHU_MCP_APP_ID` and `FEISHU_MCP_APP_SECRET` in the shell manually first.

```powershell
Get-Content .env | ForEach-Object {
  if ($_ -match '^\s*([^#][^=]+?)\s*=\s*(.*)\s*$') {
    [Environment]::SetEnvironmentVariable($matches[1].Trim(), $matches[2].Trim().Trim('"'), 'Process')
  }
}

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
$env:AGENT_PILOT_ROUTER_MODE="auto"
$env:AGENT_PILOT_AUTO_CONFIRM="true"
$env:FEISHU_TOOL_ADAPTER_TIMEOUT_SECONDS="25"
uv run python scripts/lark_event_listener.py
```

In this mode only Doc creation is attempted through official MCP `docx.builtin.import`. Slides and Canvas remain on `lark-cli`. MCP creates a new document by import; it does not directly edit an existing Doc. Any MCP startup, tool manifest, schema, authorization, or import failure is recorded with secrets redacted and then falls back to the stable `lark-cli` / fake path.

The listener keeps auto-confirmed artifact generation in the background, so
`/status` can still respond while Doc, Slides, or Canvas is running. Terminal
logs prefixed with `[Agent-Pilot]` show the routed command type and latest task
status; if a real MCP process hangs, the tool layer falls back after
`FEISHU_TOOL_ADAPTER_TIMEOUT_SECONDS`.

If you prefer `.env`-only operation, put the same non-secret mode switches in `.env`:

```dotenv
LARK_IM_MODE=real
LARK_ARTIFACT_MODE=real
FEISHU_TOOL_MODE=hybrid
FEISHU_MCP_MODE=real
FEISHU_MCP_TOKEN_MODE=user_access_token
FEISHU_MCP_USE_UAT=true
AGENT_PILOT_PLANNER_MODE=auto
AGENT_PILOT_ROUTER_MODE=auto
AGENT_PILOT_AUTO_CONFIRM=true
FEISHU_TOOL_ADAPTER_TIMEOUT_SECONDS=25
LARK_STREAM_DELAY_SECONDS=0.2
```

`AGENT_PILOT_AUTO_CONFIRM=true` makes the demo goal-driven: one IM message posts the plan and then continues directly through Doc, Slides, Canvas, and final delivery. Set it to `false` for the manual confirmation flow.

If MCP OAuth expires, refresh it with:

```powershell
npx -y @larksuiteoapi/lark-mcp login `
  -a $env:FEISHU_MCP_APP_ID `
  -s $env:FEISHU_MCP_APP_SECRET `
  --scope "offline_access docx:document"
```

For the most stable competition rehearsal, you can avoid MCP user OAuth by using app/tenant token mode:

```dotenv
FEISHU_MCP_TOKEN_MODE=tenant_access_token
FEISHU_MCP_USE_UAT=false
```

Keep the hybrid fallback enabled either way, so Doc creation falls back to `lark-cli` if MCP import cannot complete.

In Feishu IM, send:

```text
@Agent 帮我基于飞书比赛赛题，生成一份参赛方案文档和 5 页答辩汇报材料。重点突出 Agent 编排、多端协同、飞书办公套件联动和工程实现。
```

Then:

```text
确认
现在做到哪了？
修改：PPT 更突出工程实现和多端协同
在 Agent-Pilot 参赛方案最后一行添加当前时间
```

The first reply should appear immediately as a planning-status card. The full Agent plan updates into the same card after Planner Agent finishes.

Revision messages may be explicit (`修改：PPT ...`) or natural (`在参赛方案最后一行添加...`). IntentRouterAgent resolves the target artifact first; if it cannot tell whether the user means Doc, Slides, or Canvas, it asks for clarification instead of regenerating all artifacts.

Useful command checks:

```text
/help
/status
/reset
```

`/reset` clears the active task binding for the current chat, so the next long request starts a fresh demo flow.

## 5. Expected Judge-Facing Story

Explain the demo through A-F:

- A: IM captures the natural-language request.
- B: Planner Agent produces an explicit plan, an internal `ToolPlan`, and asks for confirmation.
- C: Doc and Canvas artifacts are generated from the same `ArtifactBrief`.
- D: A 5-page Slides deck is generated from that same brief.
- E: The same Feishu chat holds state, progress, tool execution records, and artifact links on desktop and mobile.
- F: Final summary and links are delivered back to IM.

## 6. Permission Fallback Story

If real Feishu Docs, Slides, or Whiteboard permissions are blocked:

- The same `LarkClient` interface remains active.
- `FakeLarkClient` writes `doc.md`, `slides.json`, and `canvas.mmd`.
- Responses include realistic artifact URLs.
- Switching all surfaces to real Feishu requires `LARK_MODE=real` and the necessary `lark-cli` scopes.
- Keeping only IM real requires `LARK_IM_MODE=real` and `LARK_ARTIFACT_MODE=fake`.
- Streaming plan replies send one interactive Bot card, then update that same card with `PATCH /open-apis/im/v1/messages/{message_id}`. If this fails, add the app permission for updating Bot messages, then restart the listener.
- Tool execution records show whether a step used MCP detection, `lark-cli`, or fake fallback, which gives the demo a clean explanation when real Feishu permissions are incomplete.
