# LLM-Powered Artifact Revision Content Rewrite

> Status: approved | Date: 2026-05-01

## 1. Problem

`build_artifact_revision_patch()` in `app/agents/artifact_revision_agent.py` is 100% keyword-based. It cannot understand natural language revision instructions. Five verified failure modes:

| Input | Result | Cause |
|-------|--------|-------|
| "在文档第二段补充工程实现细节" | Aborted | `_doc_location` returns `unknown` → `needs_clarification=True` |
| "PPT 更突出工程实现" | No visible change | Extracts only 2-word content "工程实现" |
| "画板补充错误处理分支" | Barely useful | Appends a simple node name, no subgraph |
| "把这个方案改得更适合答辩场景" | Aborted | No artifact/location keywords matched |
| "第3页加上飞书消息推送流程" | Wrong content | Entire instruction inserted as content |

Root cause: the router uses LLM (after timeout fix), but the patch generator is keyword-only. LLM's semantic understanding of the revision is discarded before patch creation.

## 2. Approach

**LLM full-content rewrite with keyword fallback.**

```
revise_task()
  ├─ Read local file content (doc.md / slides.json / canvas.mmd)
  ├─ Check token budget (content > MAX_CHARS → reject)
  ├─ Call build_llm_revision_content(instruction, current_content, kind)  ← NEW
  │   ├─ LLM available → returns (rewritten_content, change_summary)
  │   ├─ Validate output format (Markdown structure / JSON parse / Mermaid header)
  │   │   ├─ Valid → write content directly via lark_client.update_*()
  │   │   └─ Invalid → retry once, then fall back to keyword
  │   └─ LLM timeout/error → fall back to keyword build_artifact_revision_patch()
  └─ Write change_summary into RevisionRecord  ← NEW
```

Why full rewrite over structured patches:
- Competition artifacts are small (one doc + 5 slides + one canvas diagram)
- LLM sees full context, makes coherent changes
- No location-parsing fragility ("second paragraph" is natural to an LLM but impossible for regex)
- Simpler: one LLM call, one output, one write

## 3. New Function: `build_llm_revision_content`

**File**: `app/agents/artifact_revision_agent.py` (new function + format validators + prompt builders)

**Signature**:
```python
def build_llm_revision_content(
    instruction: str,
    current_content: str,
    artifact_kind: ArtifactKind,
    *,
    timeout_seconds: float = 15.0,
    max_input_chars: int = 60000,
) -> tuple[str, str]:  # (rewritten_content, change_summary)
```

**Behavior**:

1. **Token budget check**: if `len(current_content) > max_input_chars`, raise `ValueError` with message "内容过长，请指定具体要修改的段落或页面。" Caller falls back to keyword patch.
2. **Construct artifact-specific system prompt** (see below)
3. **LLM call** with `JobResearchLLM(temperature=0.3, max_tokens=8192)` — low temp for faithfulness, high enough tokens for full rewrite
4. **Parse response**: extract JSON with `content` and `change_summary` fields from LLM output
5. **Validate output format** via `_validate_rewritten_content(raw, kind)` — raises `ValueError` on failure → caller retries once, then falls back
6. **Timeout**: uses `asyncio.wait_for` / `ThreadPoolExecutor` like existing router pattern

**System prompts**:

### Doc (`artifact_kind="doc"`)
```
你是飞书文档编辑 Agent。用户对一份 Markdown 文档提出了修改意见。
你的任务是返回修改后的完整 Markdown 文档。

规则：
1. 输出的 Markdown 结构与输入保持一致（标题层级、列表、代码块等）
2. 只修改用户指定的部分，其他内容逐字保留
3. 不要添加任何解释、注释或说明文字
4. 如果用户要求在特定位置插入内容，准确定位并插入
5. 如果用户要求改写某段，保持该段的原有结构框架，只替换内容

返回格式（严格 JSON）：
{"content": "修改后的完整 Markdown 文档", "change_summary": "一句话简述做了什么修改"}
```

### Slides (`artifact_kind="slides"`)
```
你是飞书演示文稿编辑 Agent。用户对一份 JSON 格式的幻灯片文件提出了修改意见。
你的任务是返回修改后的完整 JSON 幻灯片数组。

输入和输出格式：
[{"title": "页面标题", "body": "页面正文"}, ...]

规则：
1. 保持页面数量不变，除非用户明确要求添加或删除页面
2. 保持每页的 title 不变，除非用户要求改标题
3. body 字段按用户指令修改
4. 输出的 JSON 必须是合法的 JSON 数组，每个元素必须有 title 和 body 字段
5. 不要添加其他字段，不要包装在代码块中
6. 不要添加解释文字

返回格式（严格 JSON）：
{"content": [{"title": "...", "body": "..."}, ...], "change_summary": "一句话简述做了什么修改"}
```

### Canvas (`artifact_kind="canvas"`)
```
你是飞书画板（Mermaid 架构图）编辑 Agent。用户对一份 Mermaid 流程图提出了修改意见。
你的任务是返回修改后的完整 Mermaid 代码。

规则：
1. 保持原有的 graph/flowchart 声明和整体布局
2. 按用户指令添加、删除或修改节点和连线
3. 节点标签使用双引号包裹
4. 输出的 Mermaid 代码必须是合法的 Mermaid 语法
5. 不要包装在代码块中，不要添加解释文字

返回格式（严格 JSON）：
{"content": "修改后的完整 Mermaid 代码", "change_summary": "一句话简述做了什么修改"}
```

## 4. Format Validators

**File**: `app/agents/artifact_revision_agent.py`

Three new internal functions:

```python
def _validate_rewritten_content(raw: str, kind: ArtifactKind) -> str:
    """Parse LLM JSON response, validate content shape, return extracted content string.
    Raises ValueError if format is unusable."""

def _validate_doc_content(content: str) -> str:
    """Must contain at least one '#' heading. Returns content as-is."""

def _validate_slides_content(content: object) -> str:
    """Must be a list of dicts, each with 'title' or 'body' key. Returns JSON string."""

def _validate_canvas_content(content: str) -> str:
    """Must start with 'graph' or 'flowchart'. Returns content as-is."""
```

All validators raise `ValueError` with a descriptive message on failure. This triggers the retry-or-fallback logic in the orchestrator.

## 5. Modified Flow: `revise_task()`

**File**: `app/services/orchestrator.py`

**New method**: `_overwrite_artifact_content(task, target_kind, content) -> None`

Bypasses the `apply_*_patch` functions entirely — takes the LLM-rewritten content directly and calls `lark_client.update_doc/slides/canvas()`. This is distinct from `_apply_revision_patches` which routes through the keyword patch system.

**Modified pseudocode**:
```python
def revise_task(self, task_id, instruction, *, target_artifacts=None, ...):
    # ... existing preamble ...
    for target in targets:
        current = _read_artifact_content(task, target)
        try:
            rewritten, change_summary = build_llm_revision_content(
                instruction, current or _regenerate_content(task, target), target
            )
            self._overwrite_artifact_content(task, target, rewritten)
            revision = RevisionRecord(
                revision_id=str(uuid.uuid4()),
                instruction=instruction,
                target_artifacts=targets,
                summary=change_summary,  # ← LLM-generated summary
            )
        except ValueError as exc:
            # Format validation failed or token budget exceeded
            # Retry once, then fall back to keyword
            ...
        except Exception:
            # LLM timeout or API error — fall back to keyword
            patch = build_artifact_revision_patch(instruction, target)
            if not patch.needs_clarification:
                self._apply_single_patch(task, patch)
            else:
                # clarification needed
                ...
```

**`_overwrite_artifact_content` implementation**:
```python
def _overwrite_artifact_content(
    self, task: AgentPilotTask, kind: ArtifactKind, content: str
) -> None:
    task_dir = self.state_service.task_dir(task.task_id)
    existing = _artifact_by_kind(task.artifacts, kind)
    if kind == "doc":
        artifact = self.lark_client.update_doc(task.task_id, existing, content, task_dir)
    elif kind == "slides":
        slides = json.loads(content)
        artifact = self.lark_client.update_slides(task.task_id, existing, slides, task_dir)
    else:
        artifact = self.lark_client.update_canvas(task.task_id, existing, content, task_dir)
    _replace_artifact(task, artifact)
```

`_read_artifact_content` reuses existing helpers:
- `_read_text_artifact(existing)` → str | None
- `_read_slides_artifact(existing)` → returns JSON string (not parsed list) for LLM input

**`_regenerate_content` helper** (when local file is missing):
```python
def _regenerate_content(task: AgentPilotTask, kind: ArtifactKind) -> str:
    if kind == "doc":
        return build_doc_artifact(task)
    if kind == "slides":
        return json.dumps(build_slide_artifact(task), ensure_ascii=False)
    return build_canvas_artifact(task)
```

## 6. Fallback Strategy

Three-tier resilience:

| Tier | Condition | Behavior |
|------|-----------|----------|
| 1 | LLM succeeds + format valid | Full rewrite applied, `change_summary` in revision record, user sees meaningful changes |
| 2a | LLM output fails format validation | Retry LLM once; if still invalid, fall back to keyword patch |
| 2b | LLM timeout/API error | Fall back to keyword `build_artifact_revision_patch` |
| 2c | Content exceeds token budget | Skip LLM, fall back to keyword with message "内容过长，请指定具体要修改的段落" |
| 3 | Keyword parser returns `needs_clarification=True` | Ask user to clarify target, show fallback notice |

Existing `with_fallback_notice()` prepends fallback notice for tiers 2a/2b/2c.

## 7. RevisionRecord Enhancement

**File**: `app/schemas/agent_pilot.py`

`RevisionRecord.summary` currently defaults to `""` and is populated by `_patch_summary()` with mechanical text like "已原地应用结构化修改补丁：slides: insert unknown". With LLM rewrite, `change_summary` provides a meaningful one-line description:

| Source | Example summary |
|--------|----------------|
| Keyword fallback | "已原地应用结构化修改补丁：slides: insert unknown" (unchanged) |
| LLM rewrite | "增强第 3-5 页的工程实现描述，补充了飞书消息推送流程细节" |

## 8. What Does NOT Change

- `apply_doc_patch` / `apply_slides_patch` / `apply_canvas_patch` — preserved as fallback
- `build_artifact_revision_patch` — preserved as fallback
- Router (`route_agent_pilot_message`) — unchanged
- Delivery service reply formatters — unchanged (except consuming new `change_summary`)
- LarkClient interface — unchanged (`update_doc/slides/canvas` already exist)
- `_apply_revision_patches` — preserved for keyword fallback path

## 9. Error Handling Summary

| Scenario | Handling |
|----------|----------|
| LLM timeout (15s) | Fall back to keyword patch; user sees fallback notice |
| LLM returns unparseable JSON | Retry once with stricter prompt; if still fails, fall back to keyword |
| LLM output fails format validation | Retry once; fall back to keyword |
| Content exceeds 60k chars | Reject with message; fall back to keyword |
| Local file missing | Regenerate from agent (`build_doc_artifact` etc.), then apply LLM rewrite |
| lark-cli overwrite fails | Existing error handling in `_apply_revision_patches` |
| `change_summary` missing in LLM response | Default to "已根据指令重写内容。" |

## 10. Testing Plan

| Test | What It Verifies |
|------|-----------------|
| `test_llm_rewrite_doc_appends_content` | "在文档最后一行添加时间" → time string appears at end of doc |
| `test_llm_rewrite_slides_enhances_content` | "PPT 更突出工程实现" → slide bodies contain engineering keywords |
| `test_llm_rewrite_canvas_adds_nodes` | "画板补充错误处理分支" → mermaid has new node definitions |
| `test_llm_rewrite_falls_back_on_timeout` | LLM timeout → keyword fallback used, fallback notice in reply |
| `test_llm_rewrite_falls_back_on_invalid_format` | LLM returns non-JSON → retry → fall back |
| `test_llm_rewrite_preserves_unchanged_sections` | Only changed parts modified, heading structure intact |
| `test_llm_rewrite_handles_missing_local_file` | Local file absent → regenerates from agent → rewrite applied |
| `test_llm_rewrite_rejects_oversized_content` | 70k char input → ValueError → keyword fallback |
| `test_llm_rewrite_change_summary_in_revision` | RevisionRecord.summary populated from LLM output |
| `test_validate_doc_rejects_flat_text` | Content without `#` heading → ValueError |
| `test_validate_slides_rejects_non_list` | Content not a JSON array → ValueError |
| `test_validate_canvas_rejects_non_mermaid` | Content not starting with graph/flowchart → ValueError |

Tests that mock LLM use `FakeLLM` pattern from existing `test_intent_router_agent.py`. Format validator tests are pure unit tests (no LLM needed).
