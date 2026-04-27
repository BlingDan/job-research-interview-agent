# Agent-Pilot Refactor Design

Date: 2026-04-26

## 1. North Star

This refactor exists for the Feishu/Lark competition. The product should be
judged as an award-worthy Feishu-native office collaboration Agent, not as a
generic backend API or a cleaned-up version of the old job-research project.

The core question for every implementation choice is:

```text
Will this make Agent-Pilot more convincing in the competition demo?
```

The strongest demo is:

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

## 2. Source Requirements

The official task document defines Agent-Pilot as an IM-based office
collaboration assistant. The implementation must visibly satisfy these A-F
scenarios:

| Scenario | Requirement | Agent-Pilot behavior |
| --- | --- | --- |
| A | Intent / instruction entry | Feishu IM captures natural-language task requests. |
| B | Task understanding and planning | Planner Agent decomposes the request into executable steps and tool choices. |
| C | Doc / whiteboard generation | Doc Agent creates a proposal document; Canvas Agent creates a workflow or architecture diagram. |
| D | Presentation generation | Presentation Agent creates a 5-page defense/report deck. |
| E | Multi-end collaboration | State and artifact links stay bound to the same Feishu chat so desktop and mobile clients see the same flow. |
| F | Summary and delivery | Delivery service sends final summary and links back to the same IM chat. |

The demo must make the mapping obvious. README, API responses, state names, IM
messages, and artifact titles should all reinforce this structure.

## 3. Scope

### In Scope

- Repurpose `/tasks` from job-research tasks to Agent-Pilot tasks.
- Support Feishu IM task start, confirmation, progress query, revision, and final delivery.
- Add a stateful Agent-Pilot orchestration layer.
- Generate a proposal Doc artifact.
- Generate a 5-page Slides artifact.
- Generate a Canvas/Whiteboard architecture or workflow artifact.
- Use `lark-cli` through a shared integration interface.
- Keep fake/dry-run mode for tests and blocked Feishu permissions.
- Persist task state and artifacts under `workspace/tasks/<task_id>/`.
- Keep the app runnable with `uv run uvicorn app.main:app --reload`.
- Protect the core flow with focused tests.

### Out of Scope

- Preserving old job-research `/tasks` request and response behavior.
- Building custom desktop/mobile dashboards.
- Building a complex frontend or PPT editor.
- Making Tavily search mandatory in the core path.
- Making local RAG mandatory in the core path.
- Production webhook hardening as the first IM entrypoint.
- Full offline conflict resolution.

## 4. Product Strategy

Feishu is the UI. The backend is the Agent brain and tool orchestration layer.
The user should experience the product entirely through Feishu IM, Doc, Slides,
and Canvas/Whiteboard.

The first demo should optimize for this input:

```text
@Agent 帮我基于飞书比赛赛题，生成一份参赛方案文档和 5 页答辩汇报材料。重点突出 Agent 编排、多端协同、飞书办公套件联动和工程实现。
```

Expected visible flow:

1. User sends the request in Feishu IM.
2. Agent replies with a structured plan and asks for `确认`.
3. User sends `确认`.
4. Agent reports progress in the same chat.
5. Agent creates or simulates a Feishu Doc proposal.
6. Agent creates or simulates a 5-page Feishu Slides deck.
7. Agent creates or simulates a Canvas/Whiteboard architecture diagram.
8. Agent sends final links and summary back to the same chat.
9. User can ask `现在做到哪了？`.
10. User can send `修改：...` and receive updated artifact status.

## 5. Architecture

### High-Level Flow

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
StateService
        |
        v
LarkClient interface
        |
        +--> LarkCliClient
        +--> FakeLarkClient
        |
        v
DeliveryService -> Feishu IM
```

### Main Responsibilities

`TaskMessageService`:

- Normalize incoming Feishu IM events or API requests into internal commands.
- Detect new task requests, `确认`, `现在做到哪了？`, and `修改：...`.
- Resolve the active task for a chat.

`AgentPilotOrchestrator`:

- Own the task state machine.
- Call agents in the correct order.
- Persist state after every stage.
- Route progress, confirmation, revision, delivery, and failure messages.

`StateService`:

- Save and load task state as JSON.
- Maintain a chat-to-active-task index.
- Store revisions and artifact metadata.

`PlannerAgent`:

- Produce an executable plan, not a fixed script.
- Explain artifacts and tool choices.
- Return a confirmation message for IM.
- Fall back to a deterministic plan when the LLM fails.

`DocAgent`:

- Generate a competition proposal document.
- Emphasize Agent orchestration, multi-end collaboration, Feishu suite linkage,
  and engineering implementation.
- Return both structured content and renderable Markdown/XML.

`PresentationAgent`:

- Generate a 5-page defense/report deck.
- Return slide outline and slide XML or a simplified artifact representation.
- Use a deterministic fallback deck.

`CanvasAgent`:

- Generate an architecture or workflow diagram.
- Prefer Mermaid for the first version because it is readable, testable, and can
  later be converted into Feishu Whiteboard content.
- Return diagram source and artifact metadata.

`LarkClient`:

- Define the integration boundary for IM, Doc, Slides, and Canvas/Whiteboard.
- Hide whether the action is real `lark-cli` or fake/dry-run.

`DeliveryService`:

- Format plan, progress, revision, error, and final delivery messages.
- Keep messages concise and useful inside Feishu IM.

## 6. Data Model

### Core Types

`AgentPilotTask`:

- `task_id: str`
- `chat_id: str | None`
- `message_id: str | None`
- `user_id: str | None`
- `input_text: str`
- `status: AgentPilotStatus`
- `plan: AgentPlan | None`
- `artifacts: list[ArtifactRef]`
- `revisions: list[RevisionRecord]`
- `created_at: str`
- `updated_at: str`
- `error: str | None`

`AgentPilotStatus`:

```text
CREATED
PLANNING
WAITING_CONFIRMATION
DOC_GENERATING
PRESENTATION_GENERATING
CANVAS_GENERATING
DELIVERING
DONE
REVISING
FAILED
```

`AgentPlan`:

- `summary: str`
- `steps: list[PlanStep]`
- `confirmation_prompt: str`

`PlanStep`:

- `id: str`
- `title: str`
- `goal: str`
- `agent: str`
- `tool: str`
- `expected_artifact: str | None`

`ArtifactRef`:

- `artifact_id: str`
- `kind: "doc" | "slides" | "canvas"`
- `title: str`
- `url: str | None`
- `token: str | None`
- `local_path: str | None`
- `status: "created" | "updated" | "fake" | "dry_run" | "failed"`
- `summary: str`

`RevisionRecord`:

- `revision_id: str`
- `instruction: str`
- `target_artifacts: list[str]`
- `summary: str`
- `created_at: str`

### Persistence

Use the existing `workspace` convention:

```text
workspace/
  tasks/
    <task_id>/
      state.json
      plan.json
      doc.md
      slides.json
      canvas.mmd
      artifacts.json
```

Add:

```text
workspace/
  indexes/
    chat_tasks.json
```

The index maps `chat_id` to the active `task_id` so follow-up IM commands can
find the right task.

## 7. API Design

Repurpose `/tasks` into Agent-Pilot APIs.

### `POST /tasks`

Create a task from natural-language input.

Request:

```json
{
  "message": "@Agent 帮我基于飞书比赛赛题，生成一份参赛方案文档和 5 页答辩汇报材料。",
  "chat_id": "oc_demo",
  "message_id": "om_demo",
  "user_id": "ou_demo"
}
```

Response:

```json
{
  "task_id": "task_xxx",
  "status": "WAITING_CONFIRMATION",
  "plan": {
    "summary": "我会生成参赛方案文档、5 页答辩材料和架构画板。",
    "steps": []
  },
  "artifacts": [],
  "reply": "已理解需求，计划如下... 回复「确认」后开始生成。"
}
```

### `POST /tasks/{task_id}/confirm`

Continue from `WAITING_CONFIRMATION` into artifact generation.

### `POST /tasks/{task_id}/revise`

Apply a revision instruction.

Request:

```json
{
  "instruction": "修改：PPT 更突出工程实现和多端协同"
}
```

### `GET /tasks/{task_id}`

Return current state, plan, artifacts, revisions, and error if any.

### Optional Later API: `POST /lark/events`

This can accept Feishu webhook events later. The first competition path should
use `lark-cli event +subscribe`.

## 8. IM Command Design

The same parser should support CLI event input and HTTP task input.

Command rules:

- New task: any message mentioning the Agent or matching a task-like request.
- Confirm: exact or normalized `确认`.
- Progress query: `现在做到哪了？`, `进度`, `状态`, or similar.
- Revision: messages beginning with `修改：` or `修改:`.

When no active task exists for a follow-up command, reply with a helpful message
asking the user to start a task.

## 9. Feishu Integration

### Real Path

Use discovered `lark-cli` commands:

```bash
lark-cli event +subscribe --compact
lark-cli im +messages-reply --message-id <om_xxx> --markdown <text> --as bot
lark-cli im +messages-send --chat-id <oc_xxx> --markdown <text> --as bot
lark-cli docs +create --api-version v2 --content <xml-or-markdown> --as user
lark-cli docs +update --api-version v2 --doc <doc> --content <xml-or-markdown> --as user
lark-cli slides +create --title <title> --slides <json-array> --as user
lark-cli whiteboard +update --whiteboard-token <token> --source - --input_format mermaid --as user
```

The current local environment has `lark-cli` installed, but `lark-cli doctor
--offline` reported no user login. Therefore real Doc/Slides/Whiteboard actions
must be optional.

### Fake/Dry-Run Path

`FakeLarkClient` must:

- Write artifacts to local task folders.
- Return realistic metadata with `url`, `token`, `title`, and `status`.
- Make the demo flow complete even without Feishu document permissions.
- Be the default for automated tests.

Example fake URL shape:

```text
https://fake.feishu.local/doc/<task_id>
https://fake.feishu.local/slides/<task_id>
https://fake.feishu.local/whiteboard/<task_id>
```

## 10. Error Handling

Errors should be visible but not noisy.

Rules:

- Any exception moves the task to `FAILED`.
- Persist `state.json` before returning.
- IM error messages should explain the failed stage and the next retry action.
- Internal errors must not expose API keys, tokens, or private Feishu content.
- If real `lark-cli` fails due to permissions, fall back to fake/dry-run when
  configured.

## 11. Testing Strategy

Use TDD for the refactor. High-value tests:

- Planner output parsing and fallback.
- State transitions from create to waiting confirmation.
- Confirmation path generates Doc, Slides, and Canvas artifacts.
- Progress query returns current state and artifact links.
- Revision records the instruction and updates target artifacts.
- Fake client writes local artifacts and returns realistic metadata.
- `/tasks` API behavior for create, confirm, revise, and get.
- Failure persists `FAILED` with error message.

Avoid tests that require real Feishu credentials.

## 12. Rollout Plan

Implement in vertical slices:

1. Core schemas and state service.
2. Planner and task creation.
3. Confirmation and fake artifact generation.
4. Progress query and revision behavior.
5. HTTP APIs.
6. `lark-cli` integration wrapper.
7. CLI event listener script.
8. Documentation and demo script.

Each slice should leave the app runnable and tests passing.

## 13. Success Criteria

The refactor is successful when:

- `POST /tasks` creates an Agent-Pilot task and returns an IM-ready plan.
- `确认` or the confirm API generates Doc, Slides, and Canvas artifacts.
- Progress query and revision behavior work against persisted task state.
- Fake mode can run end-to-end without Feishu credentials.
- The code structure clearly maps to Agent planning, Feishu artifacts, and IM
  delivery.
- The demo can be explained through A-F competition scenarios.

