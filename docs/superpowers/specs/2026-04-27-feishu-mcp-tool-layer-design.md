# Feishu MCP Tool Layer Design

Date: 2026-04-27

## 1. North Star

Agent-Pilot is being rebuilt for the Feishu/Lark competition. The tool layer
should make the product look and behave like a real Feishu-native Agent, not a
hardcoded automation script.

The goal of this design is to introduce Feishu MCP as the Agent-facing tool
protocol while preserving the current `lark-cli` path as the stable execution
engine for the live demo.

The winning message is:

```text
Agent-Pilot uses Feishu MCP/OpenAPI as the Agent tool protocol,
uses lark-cli as the reliable local execution bridge,
and keeps fallback artifacts so the real IM demo never breaks.
```

## 2. Source Requirements

The official task document emphasizes:

- AI Agent understanding and orchestration depth.
- Multi-end collaboration across desktop and mobile clients.
- A full office suite flow across IM, documents, presentation, and free canvas.
- A-F scenario coverage:
  - A: IM intent entry.
  - B: task understanding and planning.
  - C: document and whiteboard generation.
  - D: presentation generation.
  - E: multi-end collaboration and consistency.
  - F: summary and delivery.

The current project already has a working IM-driven flow:

```text
Feishu IM
-> TaskMessageService
-> AgentPilotOrchestrator
-> Planner / Doc / Presentation / Canvas agents
-> LarkClient
-> lark-cli or fake artifacts
```

The weak point is not basic connectivity. The weak point is that the tool layer
does not yet expose a clear Agent-native tool plan. To judges, that can look
like backend scripting instead of Agent tool-use.

## 3. Problem

`lark-cli` is excellent for local engineering:

- WebSocket event subscription is already working.
- Bot replies and card updates are already working.
- Doc, Slides, and Whiteboard command paths can be dry-run and tested.
- Windows command compatibility has already been handled.
- Permission errors are easy to catch and fallback.

However, `lark-cli` is not naturally visible to the LLM as an Agent tool
catalog. Unless wrapped, the Planner cannot explicitly reason over a typed set
of Feishu tools.

Feishu MCP solves the opposite side:

- It exposes Feishu OpenAPI capabilities as MCP tools.
- It is more natural for LLM-driven tool selection.
- It strengthens the competition story around "AI Agent as Pilot".

But MCP should not replace the current `lark-cli` path immediately because:

- The existing real IM listener is stable and already demo-proven.
- Official MCP coverage may not fully match Doc, Slides, Whiteboard, card
  updates, file operations, or event subscription needs.
- Replacing the whole integration stack would risk the live demo close to the
  competition.

## 4. Design Principle

Do not choose between MCP and `lark-cli`.

Use them at different layers:

```text
MCP = Agent-facing tool protocol and tool-planning language
lark-cli = reliable execution adapter for Feishu operations
Fake = deterministic demo fallback
```

This preserves the current working demo while making the architecture more
Agent-native and more defensible in the final presentation.

## 5. Proposed Architecture

### 5.1 High-Level Flow

```text
Feishu IM
  |
  v
TaskMessageService
  |
  v
PlannerAgent
  |
  v
ArtifactBrief + ToolPlan
  |
  v
AgentPilotOrchestrator
  |
  v
FeishuToolLayer
  |
  +--> FeishuMcpToolAdapter
  +--> LarkCliToolAdapter
  +--> FakeArtifactAdapter
  |
  v
Doc / Slides / Whiteboard / IM delivery
```

### 5.2 Tool Layer Contract

Add a tool execution boundary that is higher-level than `LarkClient`.

Current `LarkClient` methods are artifact-oriented:

```text
create_doc(task_id, title, content, task_dir)
create_slides(task_id, title, slides, task_dir)
create_canvas(task_id, title, mermaid, task_dir)
reply_message(message_id, text)
```

The new tool layer should make the Agent's intent explicit:

```text
ToolPlan
  - tool_id
  - capability
  - preferred_adapter
  - fallback_adapter
  - inputs
  - expected_output
  - competition_scenario
```

Example:

```json
{
  "tool_id": "feishu.docs.create_competition_proposal",
  "capability": "create_doc",
  "preferred_adapter": "mcp",
  "fallback_adapter": "lark_cli",
  "competition_scenario": "C",
  "inputs": {
    "title": "Agent-Pilot 参赛方案",
    "format": "markdown"
  },
  "expected_output": "A shareable Feishu Doc link"
}
```

### 5.3 ArtifactBrief

Before generating Doc, Slides, and Canvas, produce a shared `ArtifactBrief`.

The brief prevents each agent from inventing its own story and fixes the current
issue where the created Doc and Whiteboard can be technically present but
content-light.

`ArtifactBrief` should include:

- `task_summary`
- `official_requirement_mapping`
- `must_have_points`
- `good_to_have_points`
- `a_to_f_demo_mapping`
- `agent_architecture`
- `multi_end_collaboration_story`
- `feishu_suite_linkage`
- `engineering_implementation_points`
- `demo_script`
- `risk_and_fallback_story`

Doc, Slides, and Canvas agents all consume the same brief.

## 6. Component Responsibilities

### 6.1 PlannerAgent

PlannerAgent should do two things:

1. Produce the user-facing plan shown in IM.
2. Produce an internal `ToolPlan` that explains which Feishu tools will be used.

The plan must make A-F obvious:

| Scenario | Planner output should mention |
| --- | --- |
| A | IM instruction capture |
| B | task decomposition and tool choice |
| C | Doc and Whiteboard generation |
| D | Slides generation |
| E | shared chat state and desktop/mobile consistency |
| F | final IM delivery and revision entry |

### 6.2 ArtifactBriefBuilder

This is the bridge between planning and generation.

Inputs:

- Official competition requirements.
- User request.
- Planner plan.
- Current task state.
- Revision history.

Output:

- A structured brief shared by DocAgent, PresentationAgent, and CanvasAgent.

This should be deterministic enough to test, but may use LLM enrichment in
`auto` mode.

### 6.3 FeishuMcpToolAdapter

This adapter represents official Feishu MCP tools.

Responsibilities:

- Query or receive the available MCP tool manifest.
- Map internal `ToolPlan` entries to MCP tool calls.
- Normalize MCP responses into `ArtifactRef` or intermediate tool results.
- Report unsupported capabilities clearly so the router can fall back.

Initial likely uses:

- Standard OpenAPI operations that are well represented by official MCP.
- Future extensions such as task, calendar, approval, contact, or drive search.
- Competition storytelling around Agent-native tool-use.

Non-goals for the first slice:

- Replacing the IM WebSocket listener.
- Replacing every `lark-cli` command.
- Blocking the demo on MCP coverage.

### 6.4 LarkCliToolAdapter

This adapter keeps the current stable execution behavior.

Responsibilities:

- IM event subscription.
- Bot replies and interactive card updates.
- Doc creation when MCP is unsupported or insufficient.
- Slides creation.
- Whiteboard document creation and Mermaid update.
- Dry-run verification.
- Permission error handling.

This adapter can wrap the existing `LarkCliClient` rather than replacing it.

### 6.5 FakeArtifactAdapter

This remains the final fallback.

Responsibilities:

- Write local `doc.md`, `slides.json`, and `canvas.mmd`.
- Return realistic fake URLs.
- Preserve the end-to-end IM demo when real permissions are missing.
- Keep tests independent from Feishu credentials.

## 7. Routing Strategy

Use a capability router, not hardcoded if/else inside agents.

### 7.1 Modes

Recommended environment variables:

```text
FEISHU_TOOL_MODE=hybrid
FEISHU_MCP_MODE=off|dry_run|real
LARK_IM_MODE=fake|dry_run|real
LARK_ARTIFACT_MODE=fake|dry_run|real
```

`hybrid` means:

```text
try MCP when the capability is supported
else use lark-cli
else use fake fallback
```

### 7.2 Capability Routing Table

| Capability | Preferred | Fallback | Reason |
| --- | --- | --- | --- |
| IM event subscription | lark-cli | none/fake event fixture | Current listener is proven and event command requires bot identity. |
| IM reply/send | lark-cli | fake | Current card update path is working and demo-critical. |
| Planner tool manifest | MCP | static registry | MCP is valuable for Agent-native tool planning. |
| Doc creation | MCP if sufficiently supported | lark-cli -> fake | Need real Doc link; CLI path already handles v2 quirks. |
| Slides creation | lark-cli | fake | Current CLI shortcut is explicit and testable. |
| Whiteboard update | lark-cli | fake | Current flow needs document-hosted whiteboard plus Mermaid update. |
| Future task/calendar/contact tools | MCP | lark-cli where available | MCP is ideal for broad OpenAPI tool expansion. |

## 8. Data Model Additions

### 8.1 ToolPlan

```python
class ToolPlan(BaseModel):
    tool_calls: list[ToolCallPlan]


class ToolCallPlan(BaseModel):
    id: str
    scenario: Literal["A", "B", "C", "D", "E", "F"]
    capability: str
    preferred_adapter: Literal["mcp", "lark_cli", "fake"]
    fallback_adapters: list[Literal["mcp", "lark_cli", "fake"]]
    inputs: dict[str, Any]
    expected_output: str
    user_visible_reason: str
```

### 8.2 ToolExecutionRecord

```python
class ToolExecutionRecord(BaseModel):
    call_id: str
    adapter: str
    status: Literal["planned", "running", "succeeded", "fallback", "failed"]
    started_at: str | None
    finished_at: str | None
    output_ref: ArtifactRef | None
    error: str | None
```

### 8.3 ArtifactBrief

```python
class ArtifactBrief(BaseModel):
    task_summary: str
    official_requirement_mapping: dict[str, str]
    must_have_points: list[str]
    good_to_have_points: list[str]
    agent_architecture: list[str]
    multi_end_collaboration_story: list[str]
    feishu_suite_linkage: list[str]
    engineering_implementation_points: list[str]
    demo_script: list[str]
    risk_and_fallback_story: list[str]
```

## 9. Product Behavior

### 9.1 IM Planning Reply

The first user-visible reply should still be immediate:

```text
已收到需求，Planner Agent 正在解析意图、拆解任务和选择飞书工具。
```

The final plan should mention:

- Which artifacts will be produced.
- Which Feishu tools will be used.
- Which steps satisfy A-F.
- That the user can reply `确认`.

### 9.2 Confirmation Flow

After `确认`:

1. Build or refresh `ArtifactBrief`.
2. Generate the Doc content from the brief.
3. Execute Doc tool plan.
4. Generate Slides from the same brief.
5. Execute Slides tool plan.
6. Generate Canvas Mermaid from the same brief.
7. Execute Whiteboard tool plan.
8. Deliver links and fallback status in IM.

### 9.3 Fallback Visibility

If an adapter falls back, final IM delivery should be honest but calm:

```text
- Agent-Pilot 参赛方案：真实飞书文档链接
- Agent-Pilot 5 页答辩材料：fallback 链接（Slides 授权不足，已保留本地产物）
- Agent-Pilot 编排架构画板：真实飞书画板文档链接
```

This supports live demo reliability without pretending every API succeeded.

## 10. Error Handling

Rules:

- Tool failures should create `ToolExecutionRecord` entries.
- A single artifact failure should not fail the whole task if fallback is available.
- IM event subscription must always use bot identity.
- User-authenticated artifact actions must never affect the event listener
  identity.
- Do not expose tokens, app secrets, or private document content in IM errors.
- Surface actionable permission hints in logs or debug output.

## 11. Testing Strategy

Tests should avoid real Feishu credentials.

High-value tests:

- Tool router selects MCP when capability is supported.
- Tool router falls back to `lark-cli` when MCP reports unsupported.
- Tool router falls back to fake when real execution fails.
- `ArtifactBriefBuilder` covers A-F and must-have requirements.
- DocAgent uses `ArtifactBrief`, not only raw task text.
- CanvasAgent generates a multi-layer A-F architecture diagram.
- IM event listener always uses `--as bot`.
- Real artifact mode can fail one artifact and still deliver the task.

Dry-run tests:

- Validate `lark-cli` command shapes for docs, slides, whiteboard.
- Validate MCP tool call payload shape if an MCP client is available.

## 12. Rollout Plan

### Slice 1: Artifact Quality Foundation

Implement `ArtifactBriefBuilder`.

Goal:

- Fix empty or thin Doc/Canvas content.
- Make all artifacts reflect the official requirements.

This should happen before deep MCP integration because strong artifacts matter
more to the judges than the internal tool protocol.

### Slice 2: ToolPlan Schema and Static Registry

Add `ToolPlan`, `ToolCallPlan`, and a static Feishu tool registry.

Goal:

- Make Planner output tool choices explicitly.
- Use static registry even before MCP is wired.

### Slice 3: MCP Adapter Skeleton

Add `FeishuMcpToolAdapter` with capability detection and unsupported fallback.

Goal:

- Introduce MCP architecture without risking the live demo.

### Slice 4: Hybrid Router

Add `FeishuToolLayer` / `ToolRouter`.

Goal:

- Route per capability:
  - MCP where supported.
  - CLI where proven.
  - Fake where needed.

### Slice 5: Demo and Documentation

Update README and demo guide:

- Explain MCP as Agent-facing tool protocol.
- Explain `lark-cli` as reliable execution bridge.
- Show A-F mapping.
- Show real/fake fallback story.

## 13. Non-Goals

- Do not replace the working `lark-cli event +subscribe` listener.
- Do not block the competition demo on MCP availability.
- Do not remove fake/dry-run mode.
- Do not build a custom dashboard.
- Do not make MCP a magic dependency that hides actual Feishu API behavior.
- Do not introduce broad third-party integrations before Doc/Slides/Canvas
  artifacts are strong.

## 14. Success Criteria

This design is successful when:

- The plan shown in IM looks like an Agent selecting Feishu tools, not a fixed
  script.
- Generated Doc, Slides, and Canvas share one coherent competition story.
- The architecture diagram shows MCP, CLI, fallback, and A-F scenario coverage.
- Real Feishu IM remains stable.
- Real artifact creation can use available Feishu capabilities without blocking
  the demo.
- The final presentation can credibly say:

```text
Agent-Pilot combines official Feishu MCP/OpenAPI tool-use with a reliable
lark-cli execution bridge to deliver an IM-native office collaboration Agent.
```

