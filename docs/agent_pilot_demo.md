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
$env:LARK_STREAM_DELAY_SECONDS="0.2"
uv run python scripts/lark_event_listener.py
```

In Feishu IM, send:

```text
@Agent 帮我基于飞书比赛赛题，生成一份参赛方案文档和 5 页答辩汇报材料。重点突出 Agent 编排、多端协同、飞书办公套件联动和工程实现。
```

Then:

```text
确认
现在做到哪了？
修改：PPT 更突出工程实现和多端协同
```

## 5. Expected Judge-Facing Story

Explain the demo through A-F:

- A: IM captures the natural-language request.
- B: Planner Agent produces an explicit plan and asks for confirmation.
- C: Doc and Canvas artifacts are generated.
- D: A 5-page Slides deck is generated.
- E: The same Feishu chat holds state, progress, and artifact links on desktop and mobile.
- F: Final summary and links are delivered back to IM.

## 6. Permission Fallback Story

If real Feishu Docs, Slides, or Whiteboard permissions are blocked:

- The same `LarkClient` interface remains active.
- `FakeLarkClient` writes `doc.md`, `slides.json`, and `canvas.mmd`.
- Responses include realistic artifact URLs.
- Switching all surfaces to real Feishu requires `LARK_MODE=real` and the necessary `lark-cli` scopes.
- Keeping only IM real requires `LARK_IM_MODE=real` and `LARK_ARTIFACT_MODE=fake`.
- Streaming plan replies send one interactive Bot card, then update that same card with `PATCH /open-apis/im/v1/messages/{message_id}`. If this fails, add the app permission for updating Bot messages, then restart the listener.
