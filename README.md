# Agent-Pilot

Feishu/Lark-native office collaboration Agent for the **基于 IM 的办公协同智能助手** competition track.

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
        +--> DocAgent
        +--> PresentationAgent
        +--> CanvasAgent
        |
        v
LarkClient interface
        |
        +--> FakeLarkClient
        +--> LarkCliClient
```

The project uses a mixed integration strategy:

- `fake`: default mode for tests and local demos; writes local artifacts and returns realistic fake URLs.
- `dry_run`: builds real `lark-cli` commands with `--dry-run`.
- `real`: calls `lark-cli` without `--dry-run` when Feishu permissions are ready.
- `LARK_IM_MODE` and `LARK_ARTIFACT_MODE` can split IM from artifact behavior. This is the safest competition mode for real Bot verification.

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

Run local IM event bridge:

```bash
uv run python scripts/lark_event_listener.py
```

For real Feishu Bot replies while keeping Doc/Slides/Canvas stable in fake mode:

```powershell
$env:LARK_IM_MODE="real"
$env:LARK_ARTIFACT_MODE="fake"
$env:LARK_STREAM_DELAY_SECONDS="0.2"
uv run python scripts/lark_event_listener.py
```

The listener consumes `lark-cli event +subscribe --compact`, parses IM messages, and routes them into the same Agent-Pilot orchestrator used by `/tasks`.

Plan replies are streamed by sending one interactive Bot card and then updating that same card with `PATCH /open-apis/im/v1/messages/{message_id}`. If Feishu returns a permission error, enable the Bot message update permission in the developer console; the code falls back to sending the final plan as a normal text reply.

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
