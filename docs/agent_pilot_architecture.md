# Agent-Pilot Architecture

This document records the implementation details that are intentionally kept out of the README. The README is the project entrance; this file explains how Agent-Pilot works.

## Product Direction

Agent-Pilot is a Feishu/Lark-native office collaboration Agent for the **基于 IM 的办公协同智能助手** competition track.

The north star is an award-worthy demo:

```text
Feishu IM
-> Agent intent capture
-> Agent task plan
-> IM confirmation or auto-confirm
-> Feishu Doc proposal
-> Feishu Slides deck
-> Feishu Canvas/Whiteboard architecture diagram
-> final IM delivery
-> progress query and revision in the same chat
```

## Runtime Architecture

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

## Core Modules

| Module | Responsibility |
| --- | --- |
| `TaskMessageService` | Parses Feishu IM events and commands such as `确认`, `当前进度`, `修改：...`, `/reset`, and `/help`. |
| `AgentPilotOrchestrator` | Owns the task lifecycle, state transitions, progress replies, artifact generation, and final delivery. |
| `PlannerAgent` | Converts the user goal into a plan, `ArtifactBrief`, and `ToolPlan`. |
| `DocAgent` | Generates the proposal document content. |
| `PresentationAgent` | Generates the 5-page defense/report deck content. |
| `CanvasAgent` | Generates the architecture/workflow diagram content. |
| `FeishuToolLayer` | Routes artifact operations through MCP, `lark-cli`, or fake fallback. |
| `DeliveryService` | Formats final IM delivery text and artifact links. |

## State Machine

```text
CREATED
-> PLANNING
-> WAITING_CONFIRMATION
-> DOC_GENERATING
-> PRESENTATION_GENERATING
-> CANVAS_GENERATING
-> DELIVERING
-> DONE
```

Additional states:

```text
REVISING
FAILED
```

`FAILED` should include a user-facing error and enough redacted internal detail for debugging.

## Tool Layer Strategy

The project uses a mixed real/fake integration strategy so the competition demo can keep moving even when a specific Feishu permission is blocked.

| Mode | Meaning |
| --- | --- |
| `fake` | Writes local artifacts and returns realistic fake Feishu URLs. |
| `dry_run` | Builds real `lark-cli` commands with `--dry-run` where available. |
| `real` | Calls Feishu APIs through `lark-cli` or MCP when permissions are ready. |
| `hybrid` | Tries MCP where supported, then `lark-cli`, then fake fallback. |

Recommended competition setting:

```dotenv
LARK_IM_MODE=real
LARK_ARTIFACT_MODE=real
FEISHU_TOOL_MODE=hybrid
FEISHU_MCP_MODE=real
AGENT_PILOT_PLANNER_MODE=auto
AGENT_PILOT_AUTO_CONFIRM=true
LARK_STREAM_DELAY_SECONDS=0.2
```

## MCP Integration

Official Feishu MCP is currently used only for Doc creation through `docx.builtin.import`.

```text
Doc creation: MCP -> lark-cli -> fake
Slides:       lark-cli -> fake
Canvas:       lark-cli -> fake
```

MCP mode needs app credentials and user OAuth:

```powershell
npx -y @larksuiteoapi/lark-mcp login `
  -a $env:FEISHU_MCP_APP_ID `
  -s $env:FEISHU_MCP_APP_SECRET `
  --scope "offline_access docx:document"
```

If the browser shows Feishu error `20029`, add these redirect URLs in the Feishu developer console:

```text
http://localhost:3000/callback
http://localhost:3000/callback?redirect_uri=http://localhost:3000/callback
```

If user OAuth expiry is risky during rehearsal, switch MCP Doc import to tenant token mode after enabling the required app scopes:

```dotenv
FEISHU_MCP_TOKEN_MODE=tenant_access_token
FEISHU_MCP_USE_UAT=false
```

## Feishu IM Behavior

When a new task arrives, the Bot sends a planning status card immediately. After Planner Agent finishes, the card is updated with the full plan. This prevents the user from staring at an idle chat while the LLM is working.

Useful IM commands:

```text
/help
/status
/reset
确认
当前进度
修改：PPT 更突出工程实现和多端协同
```

`/reset` clears the active task binding for the current chat without deleting historical artifacts, which is useful for repeated live demos.

## Artifact Alignment

`ArtifactBrief` is generated once per task and shared by Doc, Slides, and Canvas. This keeps the three deliverables aligned with the official A-F competition scenarios instead of letting each artifact tell a different story.

`ToolPlan` records which Feishu capability each step needs, why it is user-visible, and which adapters can execute it:

```text
PlannerAgent
-> ToolPlan(create_doc, create_slides, create_canvas, deliver_im_summary)
-> FeishuToolLayer
-> MCP when available
-> lark-cli for stable live execution
-> fake artifact fallback when permission or coverage blocks the real call
```

## Detailed Runbook

See [Agent-Pilot Demo Guide](./agent_pilot_demo.md) for the full local API demo, real Feishu IM listener flow, MCP OAuth setup, and permission fallback story.
