# Agent-Pilot Refactor Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Rebuild the current job-research prototype into an award-oriented Feishu-native Agent-Pilot demo driven by IM, Agent planning, Doc, Slides, Canvas, progress queries, and revisions.

**Architecture:** Keep the FastAPI app and LLM wrapper, but replace the core domain with an Agent-Pilot state machine. All Feishu actions go through a `LarkClient` interface with fake/dry-run as the test default and `lark-cli` as the real integration path.

**Tech Stack:** Python 3.12, FastAPI, Pydantic v2, pytest, OpenAI-compatible chat API, `lark-cli`, local JSON persistence under `workspace/`.

---

## Scope Check

This plan intentionally covers one integrated vertical product: Agent-Pilot. It has several modules, but they are not independent products. Each task below leaves the repo closer to a runnable Feishu-native demo and should keep tests passing before moving on.

Do not preserve the old job-research `/tasks` API. It is explicitly replaced.

## File Structure

Create or modify these files:

- `app/schemas/agent_pilot.py`: Agent-Pilot task, plan, artifact, revision, command, and response models.
- `app/services/state_service.py`: JSON persistence and chat-to-active-task index.
- `app/services/task_message_service.py`: Parse IM/API messages into internal commands.
- `app/services/orchestrator.py`: State machine and main Agent-Pilot workflow.
- `app/services/delivery_service.py`: IM-ready text formatting for plan, progress, revision, final delivery, and errors.
- `app/agents/planner_agent.py`: Replace job-research planning with Agent-Pilot planning and fallback.
- `app/agents/doc_agent.py`: Generate proposal document content and fallback Markdown.
- `app/agents/presentation_agent.py`: Generate 5-slide deck content and fallback slide JSON.
- `app/agents/canvas_agent.py`: Generate Canvas/Whiteboard Mermaid content and fallback diagram.
- `app/integrations/lark_client.py`: Protocol/interface and common artifact result types.
- `app/integrations/fake_lark_client.py`: Test/default integration that writes local artifacts and returns fake URLs.
- `app/integrations/lark_cli_client.py`: Real `lark-cli` subprocess wrapper.
- `app/api/routers/task.py`: Replace old `/tasks` behavior with Agent-Pilot API.
- `app/core/config.py`: Add Agent-Pilot and Lark integration settings.
- `scripts/lark_event_listener.py`: Local demo bridge for `lark-cli event +subscribe`.
- `README.md`: Update product direction and quick demo commands.
- `tests/test_agent_pilot_state_service.py`: State persistence tests.
- `tests/test_task_message_service.py`: IM command parsing tests.
- `tests/test_agent_pilot_agents.py`: Agent fallback/parsing tests.
- `tests/test_fake_lark_client.py`: Fake artifact creation tests.
- `tests/test_agent_pilot_orchestrator.py`: State machine tests.
- `tests/test_agent_pilot_api.py`: FastAPI endpoint tests.
- `tests/test_lark_cli_client.py`: Subprocess command construction tests.

Retire or rewrite old job-research tests as their files are touched:

- `tests/test_planner_agent.py`
- `tests/test_planner_service.py`
- `tests/test_report_service.py`
- `tests/test_research_coordinator.py`
- `tests/test_search_service.py`
- `tests/test_summarizer_service.py`

Keep tests that still protect shared infrastructure:

- `tests/test_llm.py`
- `tests/test_rag_service.py` unless RAG dependencies become a drag.
- `tests/test_upload_router.py` unless upload is removed from the app.

---

## Task 1: Core Schemas

**Files:**

- Create: `app/schemas/agent_pilot.py`
- Test: `tests/test_agent_pilot_schemas.py`

- [ ] **Step 1: Write schema tests**

Create `tests/test_agent_pilot_schemas.py` with tests for status literals, artifact refs, and task defaults:

```python
from app.schemas.agent_pilot import AgentPilotTask, ArtifactRef, AgentPilotStatus


def test_task_defaults_start_created():
    task = AgentPilotTask(task_id="task-1", input_text="生成参赛方案")
    assert task.status == "CREATED"
    assert task.artifacts == []
    assert task.revisions == []


def test_artifact_ref_supports_fake_doc():
    artifact = ArtifactRef(
        artifact_id="artifact-1",
        kind="doc",
        title="Agent-Pilot 参赛方案",
        status="fake",
        url="https://fake.feishu.local/doc/task-1",
    )
    assert artifact.kind == "doc"
    assert artifact.status == "fake"
```

- [ ] **Step 2: Run the failing schema tests**

Run:

```bash
uv run pytest tests/test_agent_pilot_schemas.py -v
```

Expected: fail because `app.schemas.agent_pilot` does not exist.

- [ ] **Step 3: Implement schemas**

Create `app/schemas/agent_pilot.py` with:

```python
from __future__ import annotations

from datetime import datetime, timezone
from typing import Literal

from pydantic import BaseModel, Field

AgentPilotStatus = Literal[
    "CREATED",
    "PLANNING",
    "WAITING_CONFIRMATION",
    "DOC_GENERATING",
    "PRESENTATION_GENERATING",
    "CANVAS_GENERATING",
    "DELIVERING",
    "DONE",
    "REVISING",
    "FAILED",
]

ArtifactKind = Literal["doc", "slides", "canvas"]
ArtifactStatus = Literal["created", "updated", "fake", "dry_run", "failed"]
MessageCommandType = Literal["new_task", "confirm", "progress", "revise", "unknown"]


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


class PlanStep(BaseModel):
    id: str
    title: str
    goal: str
    agent: str
    tool: str
    expected_artifact: str | None = None


class AgentPlan(BaseModel):
    summary: str
    steps: list[PlanStep] = Field(default_factory=list)
    confirmation_prompt: str = "回复「确认」后我开始生成文档、汇报材料和画板。"


class ArtifactRef(BaseModel):
    artifact_id: str
    kind: ArtifactKind
    title: str
    url: str | None = None
    token: str | None = None
    local_path: str | None = None
    status: ArtifactStatus
    summary: str = ""


class RevisionRecord(BaseModel):
    revision_id: str
    instruction: str
    target_artifacts: list[ArtifactKind] = Field(default_factory=list)
    summary: str = ""
    created_at: str = Field(default_factory=utc_now)


class AgentPilotTask(BaseModel):
    task_id: str
    input_text: str
    chat_id: str | None = None
    message_id: str | None = None
    user_id: str | None = None
    status: AgentPilotStatus = "CREATED"
    plan: AgentPlan | None = None
    artifacts: list[ArtifactRef] = Field(default_factory=list)
    revisions: list[RevisionRecord] = Field(default_factory=list)
    created_at: str = Field(default_factory=utc_now)
    updated_at: str = Field(default_factory=utc_now)
    error: str | None = None


class AgentPilotCommand(BaseModel):
    type: MessageCommandType
    text: str
    chat_id: str | None = None
    message_id: str | None = None
    user_id: str | None = None
    task_id: str | None = None


class TaskCreateRequest(BaseModel):
    message: str
    chat_id: str | None = None
    message_id: str | None = None
    user_id: str | None = None


class TaskActionRequest(BaseModel):
    message: str | None = None
    instruction: str | None = None


class AgentPilotResponse(BaseModel):
    task_id: str
    status: AgentPilotStatus
    plan: AgentPlan | None = None
    artifacts: list[ArtifactRef] = Field(default_factory=list)
    reply: str
    error: str | None = None
```

- [ ] **Step 4: Run tests**

Run:

```bash
uv run pytest tests/test_agent_pilot_schemas.py -v
```

Expected: pass.

- [ ] **Step 5: Commit**

```bash
git add app/schemas/agent_pilot.py tests/test_agent_pilot_schemas.py
git commit -m "feat: add agent pilot schemas"
```

---

## Task 2: State Service

**Files:**

- Create: `app/services/state_service.py`
- Test: `tests/test_agent_pilot_state_service.py`

- [ ] **Step 1: Write state service tests**

Test save/load, chat index, status update, and missing active task.

- [ ] **Step 2: Run tests to verify failure**

```bash
uv run pytest tests/test_agent_pilot_state_service.py -v
```

Expected: fail because `StateService` does not exist.

- [ ] **Step 3: Implement `StateService`**

Required methods:

```python
class StateService:
    def __init__(self, workspace_root: str | Path = "workspace"): ...
    def task_dir(self, task_id: str) -> Path: ...
    def save_task(self, task: AgentPilotTask) -> AgentPilotTask: ...
    def load_task(self, task_id: str) -> AgentPilotTask: ...
    def bind_chat(self, chat_id: str, task_id: str) -> None: ...
    def get_active_task_id(self, chat_id: str) -> str | None: ...
    def update_status(self, task: AgentPilotTask, status: AgentPilotStatus) -> AgentPilotTask: ...
```

Implementation notes:

- Write UTF-8 JSON with `ensure_ascii=False`.
- Store task state at `workspace/tasks/<task_id>/state.json`.
- Store chat index at `workspace/indexes/chat_tasks.json`.
- Update `updated_at` on every save.

- [ ] **Step 4: Run state tests**

```bash
uv run pytest tests/test_agent_pilot_state_service.py -v
```

Expected: pass.

- [ ] **Step 5: Commit**

```bash
git add app/services/state_service.py tests/test_agent_pilot_state_service.py
git commit -m "feat: persist agent pilot task state"
```

---

## Task 3: Message Parsing

**Files:**

- Create: `app/services/task_message_service.py`
- Test: `tests/test_task_message_service.py`

- [ ] **Step 1: Write parser tests**

Cover:

- `确认` -> `confirm`
- `现在做到哪了？` -> `progress`
- `修改：PPT 更突出工程实现` -> `revise`
- demo request with `@Agent` -> `new_task`
- unknown blank text -> `unknown`

- [ ] **Step 2: Run failing parser tests**

```bash
uv run pytest tests/test_task_message_service.py -v
```

Expected: fail because service does not exist.

- [ ] **Step 3: Implement parser**

Create `TaskMessageService.parse_text(...)` and `TaskMessageService.parse_lark_event(...)`.

Minimum behavior:

```python
def parse_text(self, text: str, *, chat_id=None, message_id=None, user_id=None) -> AgentPilotCommand:
    normalized = text.strip()
    if normalized == "确认":
        command_type = "confirm"
    elif normalized in {"现在做到哪了？", "现在做到哪了?", "进度", "状态"}:
        command_type = "progress"
    elif normalized.startswith(("修改：", "修改:")):
        command_type = "revise"
    elif normalized:
        command_type = "new_task"
    else:
        command_type = "unknown"
    return AgentPilotCommand(...)
```

For `parse_lark_event`, support compact event keys from `lark-cli event +subscribe --compact` and tolerate raw event dictionaries.

- [ ] **Step 4: Run parser tests**

```bash
uv run pytest tests/test_task_message_service.py -v
```

Expected: pass.

- [ ] **Step 5: Commit**

```bash
git add app/services/task_message_service.py tests/test_task_message_service.py
git commit -m "feat: parse agent pilot IM commands"
```

---

## Task 4: Planner Agent

**Files:**

- Modify: `app/agents/planner_agent.py`
- Create or modify: `tests/test_agent_pilot_agents.py`
- Retire or rewrite: `tests/test_planner_agent.py`, `tests/test_planner_service.py`

- [ ] **Step 1: Write planner tests**

Test:

- fallback plan has Doc, Slides, and Canvas steps.
- plan asks for confirmation.
- parsed LLM JSON becomes `AgentPlan`.

- [ ] **Step 2: Run planner tests**

```bash
uv run pytest tests/test_agent_pilot_agents.py -k planner -v
```

Expected: fail until Agent-Pilot planner exists.

- [ ] **Step 3: Replace planner behavior**

`app/agents/planner_agent.py` should export:

```python
def build_agent_plan(user_message: str) -> AgentPlan: ...
def parse_plan_output(raw_text: str) -> AgentPlan: ...
def build_fallback_plan(user_message: str) -> AgentPlan: ...
```

Fallback plan must include:

- `doc_agent` step for Feishu Doc proposal.
- `presentation_agent` step for 5-page Slides.
- `canvas_agent` step for architecture/workflow Canvas.
- `delivery_service` step for IM summary delivery.

- [ ] **Step 4: Update old planner tests**

Either rewrite old tests to Agent-Pilot planner expectations or remove them if fully superseded.

- [ ] **Step 5: Run planner-related tests**

```bash
uv run pytest tests/test_agent_pilot_agents.py tests/test_planner_agent.py tests/test_planner_service.py -v
```

Expected: pass after test migration.

- [ ] **Step 6: Commit**

```bash
git add app/agents/planner_agent.py tests/test_agent_pilot_agents.py tests/test_planner_agent.py tests/test_planner_service.py
git commit -m "feat: plan agent pilot tasks"
```

---

## Task 5: Artifact Agents

**Files:**

- Create: `app/agents/doc_agent.py`
- Create: `app/agents/presentation_agent.py`
- Create: `app/agents/canvas_agent.py`
- Test: `tests/test_agent_pilot_agents.py`
- Retire or rewrite: `tests/test_report_service.py`, `tests/test_summarizer_service.py`

- [ ] **Step 1: Write artifact agent tests**

Test deterministic fallbacks:

- Doc content contains "Agent 编排", "多端协同", "飞书办公套件联动", "工程实现".
- Slides output has exactly 5 pages.
- Canvas output is Mermaid and includes IM, Planner, Doc, Slides, Canvas, Delivery.

- [ ] **Step 2: Run failing tests**

```bash
uv run pytest tests/test_agent_pilot_agents.py -k "doc or presentation or canvas" -v
```

Expected: fail because agents do not exist.

- [ ] **Step 3: Implement `DocAgent`**

Minimum exports:

```python
def build_doc_artifact(task: AgentPilotTask) -> str: ...
def build_fallback_doc(task: AgentPilotTask) -> str: ...
```

Return Markdown first. Keep XML conversion for later if needed.

- [ ] **Step 4: Implement `PresentationAgent`**

Minimum exports:

```python
def build_slide_artifact(task: AgentPilotTask) -> list[dict[str, str]]: ...
def build_fallback_slides(task: AgentPilotTask) -> list[dict[str, str]]: ...
```

Fallback slide titles:

1. Agent-Pilot: 基于 IM 的办公协同智能助手
2. 场景闭环: 从 IM 到 Doc/Slides/Canvas
3. Agent 编排: 状态机与工具调用
4. 多端协同: Feishu 作为统一 UI
5. 工程实现与演示路径

- [ ] **Step 5: Implement `CanvasAgent`**

Minimum exports:

```python
def build_canvas_artifact(task: AgentPilotTask) -> str: ...
def build_fallback_canvas(task: AgentPilotTask) -> str: ...
```

Return Mermaid flowchart.

- [ ] **Step 6: Migrate old report/summarizer tests**

Rewrite or remove tests that assert job-interview reports.

- [ ] **Step 7: Run artifact tests**

```bash
uv run pytest tests/test_agent_pilot_agents.py tests/test_report_service.py tests/test_summarizer_service.py -v
```

Expected: pass.

- [ ] **Step 8: Commit**

```bash
git add app/agents/doc_agent.py app/agents/presentation_agent.py app/agents/canvas_agent.py tests/test_agent_pilot_agents.py tests/test_report_service.py tests/test_summarizer_service.py
git commit -m "feat: generate agent pilot artifacts"
```

---

## Task 6: Lark Client Interface and Fake Client

**Files:**

- Create: `app/integrations/lark_client.py`
- Create: `app/integrations/fake_lark_client.py`
- Test: `tests/test_fake_lark_client.py`

- [ ] **Step 1: Write fake client tests**

Test:

- `create_doc` writes `doc.md` and returns fake doc URL.
- `create_slides` writes `slides.json` and returns fake slides URL.
- `create_canvas` writes `canvas.mmd` and returns fake whiteboard URL.
- `send_message` returns metadata without requiring credentials.

- [ ] **Step 2: Run failing tests**

```bash
uv run pytest tests/test_fake_lark_client.py -v
```

Expected: fail because integrations do not exist.

- [ ] **Step 3: Implement interface**

Use a `Protocol`:

```python
class LarkClient(Protocol):
    def send_message(self, chat_id: str, text: str) -> dict: ...
    def reply_message(self, message_id: str, text: str) -> dict: ...
    def create_doc(self, task_id: str, title: str, content: str, task_dir: Path) -> ArtifactRef: ...
    def create_slides(self, task_id: str, title: str, slides: list[dict], task_dir: Path) -> ArtifactRef: ...
    def create_canvas(self, task_id: str, title: str, mermaid: str, task_dir: Path) -> ArtifactRef: ...
```

- [ ] **Step 4: Implement fake client**

Fake URL examples:

```text
https://fake.feishu.local/doc/<task_id>
https://fake.feishu.local/slides/<task_id>
https://fake.feishu.local/whiteboard/<task_id>
```

- [ ] **Step 5: Run fake client tests**

```bash
uv run pytest tests/test_fake_lark_client.py -v
```

Expected: pass.

- [ ] **Step 6: Commit**

```bash
git add app/integrations/lark_client.py app/integrations/fake_lark_client.py tests/test_fake_lark_client.py
git commit -m "feat: add fake lark client"
```

---

## Task 7: Delivery Service

**Files:**

- Create: `app/services/delivery_service.py`
- Test: `tests/test_delivery_service.py`

- [ ] **Step 1: Write delivery formatting tests**

Cover:

- plan reply includes confirmation instruction.
- progress reply includes status and next action.
- final reply includes all artifact links.
- failed reply includes user-facing error.

- [ ] **Step 2: Run failing tests**

```bash
uv run pytest tests/test_delivery_service.py -v
```

Expected: fail.

- [ ] **Step 3: Implement service**

Exports:

```python
def format_plan_reply(task: AgentPilotTask) -> str: ...
def format_progress_reply(task: AgentPilotTask) -> str: ...
def format_final_reply(task: AgentPilotTask) -> str: ...
def format_revision_reply(task: AgentPilotTask, revision: RevisionRecord) -> str: ...
def format_error_reply(task: AgentPilotTask) -> str: ...
```

Keep IM messages concise and competition-friendly.

- [ ] **Step 4: Run tests**

```bash
uv run pytest tests/test_delivery_service.py -v
```

Expected: pass.

- [ ] **Step 5: Commit**

```bash
git add app/services/delivery_service.py tests/test_delivery_service.py
git commit -m "feat: format agent pilot IM replies"
```

---

## Task 8: Orchestrator

**Files:**

- Create: `app/services/orchestrator.py`
- Modify only if needed: `app/services/orchestration_service.py`
- Test: `tests/test_agent_pilot_orchestrator.py`
- Retire or rewrite: `tests/test_research_coordinator.py`

- [ ] **Step 1: Write orchestrator tests**

Test:

- `create_task` persists `WAITING_CONFIRMATION`.
- `confirm_task` generates doc, slides, and canvas artifacts.
- `get_progress` returns IM-ready status.
- `revise_task` records revision and updates relevant artifacts.
- failure persists `FAILED`.

- [ ] **Step 2: Run failing orchestrator tests**

```bash
uv run pytest tests/test_agent_pilot_orchestrator.py -v
```

Expected: fail.

- [ ] **Step 3: Implement orchestrator**

Class shape:

```python
class AgentPilotOrchestrator:
    def __init__(self, state_service: StateService, lark_client: LarkClient): ...
    def create_task(self, request: TaskCreateRequest) -> AgentPilotResponse: ...
    def confirm_task(self, task_id: str) -> AgentPilotResponse: ...
    def get_task(self, task_id: str) -> AgentPilotResponse: ...
    def get_progress(self, task_id: str) -> AgentPilotResponse: ...
    def revise_task(self, task_id: str, instruction: str) -> AgentPilotResponse: ...
```

Confirm flow:

```text
WAITING_CONFIRMATION
-> DOC_GENERATING
-> PRESENTATION_GENERATING
-> CANVAS_GENERATING
-> DELIVERING
-> DONE
```

- [ ] **Step 4: Migrate research coordinator tests**

Rewrite old research coordinator tests to Agent-Pilot orchestrator expectations.

- [ ] **Step 5: Run orchestrator tests**

```bash
uv run pytest tests/test_agent_pilot_orchestrator.py tests/test_research_coordinator.py -v
```

Expected: pass.

- [ ] **Step 6: Commit**

```bash
git add app/services/orchestrator.py app/services/orchestration_service.py tests/test_agent_pilot_orchestrator.py tests/test_research_coordinator.py
git commit -m "feat: orchestrate agent pilot workflow"
```

---

## Task 9: API Routes

**Files:**

- Modify: `app/api/routers/task.py`
- Modify: `app/schemas/task.py` or replace imports with `app/schemas/agent_pilot.py`
- Test: `tests/test_agent_pilot_api.py`

- [ ] **Step 1: Write API tests**

Use FastAPI `TestClient`.

Cover:

- `POST /tasks` returns `WAITING_CONFIRMATION`.
- `POST /tasks/{task_id}/confirm` returns `DONE` with 3 artifacts.
- `POST /tasks/{task_id}/revise` returns `REVISING` or `DONE` with revision record.
- `GET /tasks/{task_id}` returns persisted state.

- [ ] **Step 2: Run failing API tests**

```bash
uv run pytest tests/test_agent_pilot_api.py -v
```

Expected: fail until router is updated.

- [ ] **Step 3: Update route dependencies**

Use fake client by default. Add a small factory:

```python
def build_orchestrator() -> AgentPilotOrchestrator:
    settings = get_settings()
    state_service = StateService(settings.workspace_root)
    lark_client = FakeLarkClient()
    return AgentPilotOrchestrator(state_service, lark_client)
```

Later tasks can switch this based on settings.

- [ ] **Step 4: Replace old `/tasks` behavior**

Do not keep `TaskCreateRequest(jd_text=...)` behavior.

- [ ] **Step 5: Run API tests**

```bash
uv run pytest tests/test_agent_pilot_api.py -v
```

Expected: pass.

- [ ] **Step 6: Commit**

```bash
git add app/api/routers/task.py app/schemas/task.py tests/test_agent_pilot_api.py
git commit -m "feat: expose agent pilot task api"
```

---

## Task 10: Configuration

**Files:**

- Modify: `app/core/config.py`
- Test: `tests/test_agent_pilot_config.py`

- [ ] **Step 1: Write config tests**

Test defaults:

- `lark_mode == "fake"`
- `agent_pilot_default_chat_id is None`
- workspace remains `workspace`

- [ ] **Step 2: Run failing config tests**

```bash
uv run pytest tests/test_agent_pilot_config.py -v
```

Expected: fail until fields exist.

- [ ] **Step 3: Add config fields**

Add:

```python
lark_mode: Literal["fake", "dry_run", "real"] = "fake"
lark_cli_timeout_seconds: float = 30.0
agent_pilot_default_chat_id: str | None = None
```

- [ ] **Step 4: Wire API factory to config**

Use fake client for `fake` and `dry_run` until real client lands.

- [ ] **Step 5: Run config/API tests**

```bash
uv run pytest tests/test_agent_pilot_config.py tests/test_agent_pilot_api.py -v
```

Expected: pass.

- [ ] **Step 6: Commit**

```bash
git add app/core/config.py tests/test_agent_pilot_config.py app/api/routers/task.py
git commit -m "feat: configure agent pilot integration mode"
```

---

## Task 11: Lark CLI Client

**Files:**

- Create: `app/integrations/lark_cli_client.py`
- Test: `tests/test_lark_cli_client.py`

- [ ] **Step 1: Write subprocess construction tests**

Monkeypatch `subprocess.run`. Do not call real `lark-cli`.

Test commands include:

- `im +messages-send`
- `im +messages-reply`
- `docs +create --api-version v2`
- `slides +create`

- [ ] **Step 2: Run failing tests**

```bash
uv run pytest tests/test_lark_cli_client.py -v
```

Expected: fail.

- [ ] **Step 3: Implement `LarkCliClient`**

Requirements:

- Accept `dry_run: bool`.
- Use list arguments, not shell strings.
- Return parsed JSON when possible.
- Convert permission failures into clear exceptions.
- In `dry_run`, append `--dry-run` where supported.

- [ ] **Step 4: Add artifact methods**

Implement:

- `create_doc`
- `create_slides`
- `create_canvas`
- `send_message`
- `reply_message`

For `create_canvas`, first version may return dry-run/fake metadata if no board token exists. Do not block the whole flow on Whiteboard permissions.

- [ ] **Step 5: Run CLI client tests**

```bash
uv run pytest tests/test_lark_cli_client.py -v
```

Expected: pass without real credentials.

- [ ] **Step 6: Commit**

```bash
git add app/integrations/lark_cli_client.py tests/test_lark_cli_client.py
git commit -m "feat: add lark cli integration client"
```

---

## Task 12: CLI Event Listener Script

**Files:**

- Create: `scripts/lark_event_listener.py`
- Test: `tests/test_lark_event_listener.py`

- [ ] **Step 1: Write listener tests**

Test that one NDJSON event line is parsed and routed through `TaskMessageService`.

- [ ] **Step 2: Run failing tests**

```bash
uv run pytest tests/test_lark_event_listener.py -v
```

Expected: fail.

- [ ] **Step 3: Implement script**

Behavior:

- Spawn `lark-cli event +subscribe --compact`.
- Read stdout line by line.
- Parse JSON.
- Convert event to command.
- Call orchestrator.
- Reply through configured Lark client.

Add a testable function:

```python
def handle_event_line(line: str, orchestrator: AgentPilotOrchestrator, message_service: TaskMessageService) -> AgentPilotResponse | None:
    ...
```

- [ ] **Step 4: Add run command docs in script docstring**

```bash
uv run python scripts/lark_event_listener.py
```

- [ ] **Step 5: Run listener tests**

```bash
uv run pytest tests/test_lark_event_listener.py -v
```

Expected: pass.

- [ ] **Step 6: Commit**

```bash
git add scripts/lark_event_listener.py tests/test_lark_event_listener.py
git commit -m "feat: add lark event listener"
```

---

## Task 13: Full Test Migration

**Files:**

- Modify tests as needed under `tests/`
- Possibly keep legacy services untouched if not imported by app.

- [ ] **Step 1: Run full test suite**

```bash
uv run pytest
```

Expected: likely failures in old job-research tests.

- [ ] **Step 2: Classify failures**

For each failure, decide:

- Shared infrastructure test: fix code.
- Old product behavior test: rewrite to Agent-Pilot.
- Dead legacy behavior: remove the test only after an equivalent Agent-Pilot test exists.

- [ ] **Step 3: Update tests**

Keep test count healthy. Do not delete broad coverage without replacement.

- [ ] **Step 4: Run full test suite again**

```bash
uv run pytest
```

Expected: pass.

- [ ] **Step 5: Commit**

```bash
git add tests app
git commit -m "test: align suite with agent pilot"
```

---

## Task 14: Documentation and Demo Script

**Files:**

- Modify: `README.md`
- Create: `docs/agent_pilot_demo.md`
- Optionally create: `docs/codex_audit.md`, `docs/revised_scope.md` if still useful.

- [ ] **Step 1: Update README**

README should say this is Agent-Pilot, not Job Research Interview Agent.

Include:

- product goal.
- Feishu is the UI.
- A-F scenario mapping.
- quick start.
- fake mode demo.
- real IM listener command.

- [ ] **Step 2: Write demo doc**

Create `docs/agent_pilot_demo.md` with:

- preflight: `lark-cli doctor --offline`.
- start app command.
- fake API demo commands.
- real `lark-cli event +subscribe` listener command.
- exact demo input.
- expected IM sequence.
- fallback story when Doc/Slides/Canvas permissions are blocked.

- [ ] **Step 3: Run docs sanity checks**

Run:

```bash
uv run pytest
```

Expected: pass.

- [ ] **Step 4: Commit**

```bash
git add README.md docs/agent_pilot_demo.md
git commit -m "docs: document agent pilot demo"
```

---

## Task 15: Manual Verification

**Files:**

- No code changes unless verification reveals bugs.

- [ ] **Step 1: Start the API**

```bash
uv run uvicorn app.main:app --reload
```

Expected: app starts with title updated or still runnable.

- [ ] **Step 2: Create fake task through API**

Use PowerShell:

```powershell
$body = @{
  message = "@Agent 帮我基于飞书比赛赛题，生成一份参赛方案文档和 5 页答辩汇报材料。重点突出 Agent 编排、多端协同、飞书办公套件联动和工程实现。"
  chat_id = "oc_demo"
  message_id = "om_demo"
  user_id = "ou_demo"
} | ConvertTo-Json

Invoke-RestMethod -Method Post -Uri http://127.0.0.1:8000/tasks -ContentType "application/json" -Body $body
```

Expected: `WAITING_CONFIRMATION`.

- [ ] **Step 3: Confirm**

```powershell
Invoke-RestMethod -Method Post -Uri http://127.0.0.1:8000/tasks/<task_id>/confirm
```

Expected: `DONE` and 3 artifacts.

- [ ] **Step 4: Inspect artifacts**

Check:

```text
workspace/tasks/<task_id>/doc.md
workspace/tasks/<task_id>/slides.json
workspace/tasks/<task_id>/canvas.mmd
workspace/tasks/<task_id>/state.json
```

- [ ] **Step 5: Test revision**

```powershell
$body = @{ instruction = "修改：PPT 更突出工程实现和多端协同" } | ConvertTo-Json
Invoke-RestMethod -Method Post -Uri http://127.0.0.1:8000/tasks/<task_id>/revise -ContentType "application/json" -Body $body
```

Expected: revision recorded and reply explains updated artifacts.

- [ ] **Step 6: Final full test**

```bash
uv run pytest
```

Expected: pass.

- [ ] **Step 7: Commit fixes if any**

```bash
git add app tests docs README.md
git commit -m "fix: verify agent pilot demo flow"
```

---

## Execution Notes

- Keep `FakeLarkClient` as the default until real Feishu permissions are confirmed.
- Do not block core demo on Doc/Slides/Whiteboard permissions.
- Do not leak `.env`, tokens, private Feishu messages, or private document content.
- Prefer vertical slices over large refactors.
- After each task, run the narrow tests first, then periodically run `uv run pytest`.
- If old modules are no longer used by the app and are not worth migrating, leave them untouched until a cleanup task; do not mix cleanup with core demo work.

