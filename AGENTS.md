# AGENTS.md

## MCP Code Search Tooling

Use `mcp__ace_tool__search_context` as the primary semantic code search tool.
The display name may appear as `ace-tool`, but the callable MCP namespace uses
underscores, not hyphens. Do not call `mcp__ace-tool__search_context`.

Use `mcp__fast_context__fast_context_search` only as a fallback when ace-tool
cannot satisfy the semantic search request. The display name may appear as
`fast-context`, but the callable MCP namespace is `fast_context`.

Recommended project path format on Windows:

```text
E:/codespace/job-research-interview-agent
```

If ace-tool returns an indexing error such as `all files failed to upload` or
`所有文件上传失败`, do not retry the same call repeatedly. Try fast-context if
`WINDSURF_API_KEY` is configured; otherwise fall back to local file search such
as `rg` or PowerShell `Select-String`.

## North Star

Every product, architecture, and implementation decision must start from one question:

```text
Will this make Agent-Pilot a more capable and intuitive Feishu-native
office collaboration Agent?
```

## Product Goal

Turn this runnable repo into **Agent-Pilot**, a Feishu/Lark-native office
collaboration agent.

The core product flow is:

```text
Feishu IM
-> Agent intent capture
-> Agent plan (quick LLM call, structured markdown reply in IM)
-> IM confirmation (简短确认 or auto-confirm)
-> Agent sends interactive card: "正在生成方案..."
-> Doc + Slides + Canvas generated IN PARALLEL (threads)
   (independent artifacts, no reason to queue)
-> Agent update_message: card now shows all links
-> progress query and revision in the same chat
```

The demo impact: "@Agent 生成方案" → [plan in 3-5s] → 确认 → "正在生成" card
→ [parallel generation 10-15s] → card updates with all links. Under 20 seconds
total. No Canvas-as-dashboard, no HTML page, no leaving IM.

## Product Rule

**Feishu is the UI.**

The entire user experience lives inside Feishu. Do not build a standalone web
dashboard, custom desktop app, or browser-based workbench — pulling the user out
of Feishu to a separate page contradicts the "IM-based" narrative.

Feishu surfaces and their roles:

| Surface | Role |
|---------|------|
| **IM** | Entry, interaction, AND progress visualization. All user-facing status lives here. |
| **Doc** | Generated proposal document. Editable by user after creation. |
| **Slides** | Generated 5-page defense/report deck. |
| **Canvas/Whiteboard** | Generated architecture or workflow diagram (Mermaid). |
| **Backend** | Agent brain, orchestration, state, tool calls. |

### How to show Agent progress inside IM (no separate dashboard)

Send a single interactive card (`msg_type: interactive`) when task execution
starts. When all artifacts are complete, update the same card with links.

The real key is not the card — it's **parallel artifact generation**.
Doc, Slides, and Canvas are independent. Generating them sequentially wastes
30+ seconds of demo time with the user staring at "generating...". Generate
them concurrently (threads or asyncio), then deliver all links at once.

The card pattern:
1. Task confirmed → send card "正在分析需求并生成方案..."
2. All artifacts complete → `update_message` to show the delivery receipt
   with Doc/Slides/Canvas links in one shot.

## Feature Scenario Mapping (aligned with A-F requirements)

Keep the implementation and demo aligned with the official A-F scenarios:

| Scenario | Meaning | Agent-Pilot implementation |
| --- | --- | --- |
| A | Intent / instruction entry | Capture natural-language IM messages from group or direct chat. |
| B | Task understanding and planning | Planner Agent decomposes the request into executable steps and tool choices. |
| C | Doc / whiteboard generation | Generate a Feishu Doc proposal and a Canvas/Whiteboard diagram. |
| D | Presentation generation | Generate a 5-page Feishu Slides deck. |
| E | Multi-end collaboration | Keep state, artifacts, revisions, and links bound to the same Feishu chat. |
| F | Summary and delivery | Send final summary and artifact links back to the same IM thread/chat. |

The demo must make these mappings clear to users.

## Refactor Direction

The old job-research/interview-prep product direction is no longer the core
product. It may be reused only when it directly helps Agent-Pilot.

Repurpose `/tasks` into Agent-Pilot APIs. It does not need to preserve old
job-research request/response behavior.

Reusable assets from the current repo:

- FastAPI app structure.
- OpenAI-compatible LLM wrapper.
- JSON parsing and fallback patterns.
- Workspace artifact persistence.
- Test style and pytest setup.

Non-core or removable from the main path:

- Tavily web search as a required step.
- Local RAG as a required step.
- Job JD, company research, and interview-specific schemas.
- Browser/SSE/dashboard-style progress UI that pulls the user outside Feishu.
  Progress visualization should happen on Feishu surfaces (Canvas status board,
  rich IM cards, live-updated Doc) instead.

## Required Capabilities

- Start a task from Feishu IM natural language.
- Plan the task with an Agent, not a fixed script.
- Send the plan to IM and wait for `确认`.
- Support `现在做到哪了？` for progress queries.
- Support `修改：...` for revisions.
- Generate or update a Feishu Doc proposal.
- Generate a 5-page Feishu Slides deck.
- Generate a Canvas/Whiteboard architecture or workflow artifact.
- Send live progress updates by mutating a single interactive card via
  `update_message` — each pipeline stage adds a checkmark and artifact link
  to the same card, so the user watches progress in real time without leaving IM.
- Send final artifact links and summary back to the same IM chat.
- Demonstrate desktop/mobile consistency through the same Feishu chat and
  artifacts.

## Demo Input

Optimize the first-class path for:

```text
@Agent 帮我生成一份智能客服系统的产品方案文档和 5 页项目汇报材料。重点突出 Agent 编排、多端协同、飞书办公套件联动和工程实现。
```

## Agent Behavior

Planner behavior:

- Parse user intent from IM text.
- Produce a clear plan with stages, expected artifacts, and tool choices.
- Ask for confirmation before artifact generation.
- Avoid hardcoded single-path behavior; the plan should explain why Doc, Slides,
  and Canvas/Whiteboard are needed.

Revision behavior:

- Treat `修改：...` as a task-level revision request.
- Decide which artifact(s) need updates.
- Preserve previous task context and artifact links.
- Report what changed back to IM.

Progress behavior:

- Treat `现在做到哪了？` as a status query.
- Return current state, completed stages, pending stages, artifact links if any,
  and the next action.

## State Flow

Use an explicit state machine:

```text
CREATED
-> PLANNING
-> WAITING_CONFIRMATION
-> GENERATING (Doc + Slides + Canvas in parallel)
-> DELIVERING
-> DONE
```

Also support:

```text
REVISING
FAILED
```

`FAILED` must include a clear user-facing error message and enough internal
detail for debugging without exposing secrets.

## Feishu Integration Strategy

Use `lark-cli` first. Inspect actual commands with `--help` or `schema` before
hardcoding request shapes.

First integration path:

- IM entry: `lark-cli event +subscribe` reads Feishu event NDJSON.
- IM reply/send: `lark-cli im +messages-reply` and `lark-cli im +messages-send`.
- Doc: `lark-cli docs +create/update --api-version v2` when permissions are
  available.
- Slides: `lark-cli slides +create` when permissions are available.
- Canvas/Whiteboard: `lark-cli docs +update` to create a board, then
  `lark-cli whiteboard +update` when permissions are available.

Use a mixed real/fake integration model:

- Real Feishu IM Bot is the preferred demo entry.
- Doc/Slides/Canvas go through a shared `LarkClient` interface.
- If real permissions are available, create real Feishu artifacts.
- If permissions are blocked, use fake/dry-run mode and generate local artifacts
  plus realistic artifact metadata.
- Tests must use fake clients by default.

Never commit secrets, tokens, private chat data, or private Feishu document
content.

## Suggested Modules

Add or replace modules as needed to serve the Agent-Pilot flow:

```text
app/agents/planner_agent.py
app/agents/doc_agent.py
app/agents/presentation_agent.py
app/agents/canvas_agent.py

app/services/orchestrator.py
app/services/state_service.py
app/services/task_message_service.py
app/services/delivery_service.py

app/integrations/lark_client.py
app/integrations/lark_cli_client.py
app/integrations/fake_lark_client.py
```

Expected API direction:

```text
POST /tasks
POST /tasks/{task_id}/confirm
POST /tasks/{task_id}/revise
GET  /tasks/{task_id}
```

Optional later API:

```text
POST /lark/events
```

The first IM entrypoint should still be the local `lark-cli event +subscribe`
flow unless a production webhook is explicitly requested.

## Hard Rules

- Keep the app runnable at every step.
- Prefer small, reviewable changes, unless a larger change clearly improves the
  product demo.
- Do not preserve old abstractions merely because they exist.
- Do not build a standalone web dashboard, custom desktop app, or mobile app.
  All user-facing UI lives inside Feishu (IM, Doc, Slides, Canvas).
- Do not build a polished PPT editor.
- Do not make Tavily/RAG mandatory in the core demo path.
- Keep fake/dry-run mode for tests, local demos, and blocked Feishu calls.
- Use explicit, testable state transitions.

## Preferred Commands

Use `uv` first:

```bash
uv run uvicorn app.main:app --reload
uv run pytest
uv run python scripts/<script>.py
```

Fallback to existing repo commands only if `uv` is unavailable.

Useful Feishu command discovery:

```bash
lark-cli --help
lark-cli im --help
lark-cli docs --help
lark-cli slides --help
lark-cli whiteboard --help
lark-cli event +subscribe --help
lark-cli doctor --offline
```

## Definition of Done

A change is not complete unless it helps one of these outcomes:

- The Feishu IM demo flow is easier to run.
- The Agent planning behavior is more convincing.
- Doc, Slides, or Canvas artifact generation is more complete.
- Progress query, confirmation, or revision behavior is more reliable.
- The A-F feature scenario mapping is clearer.
- Tests protect the fake/dry-run path and core state transitions.

When tradeoffs appear, choose the option that creates the most compelling product experience while keeping the app runnable.
