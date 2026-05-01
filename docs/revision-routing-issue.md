# Agent-Pilot 修改意图误路由问题记录

## 背景

在已完成初版 Doc、PPT/Slides、Canvas/Whiteboard 后，用户在同一飞书 IM 会话中提出局部修改，例如：

```text
在 Agent-Pilot 参赛方案 中的最后一行添加现在的时间YY-MM-DD HH:MM
```

期望行为是只修改用户明确指向的飞书文档 Doc。

实际表现是 Agent 重新规划了一套完整任务，或者在 revision 流程里把 Doc、Slides、Canvas 一起重生成。

## 根因

问题不是单纯的模型能力问题，而是流程和 prompt 共同导致：

1. `TaskMessageService` 只把以 `修改：` 或 `修改:` 开头的消息识别为 revision。无前缀但明显是编辑既有产物的句子会被识别为 `new_task`。
2. `AgentPilotOrchestrator.handle_command` 对 `new_task` 会直接进入 `create_task`，触发完整 planner 流程。
3. planner prompt 和 fallback plan 都强调 Doc、Slides、Canvas 全链路产物，因此一旦误入新任务路径，就会自然规划三份产物。
4. revision 的 `_target_artifacts` 识别不到目标时默认返回 `["doc", "slides", "canvas"]`，导致模糊修改扩散成全量重生成。

## 修复

本次修复分两步完成：先用 deterministic fallback 止血，再补上 `IntentRouterAgent` 做语义路由。

1. 新增 `IntentRouterAgent`：将 IM 文本路由成结构化结果，包括 `command_type`、`target_artifacts`、`confidence`、`needs_clarification` 和 `reason`。
2. 保留 deterministic fallback：测试、离线 demo、LLM 不可用时仍能识别常见修改表达。
3. 增强修改意图识别：支持“在某个文档/方案/PPT/画板中添加、调整、删除、替换”等无前缀表达。
4. 增强目标产物推断：`最后一行`、`文末`、`段落`、`正文` 等文档位置提示会推断为 `doc`，不会触发 Slides/Canvas。
5. 取消模糊 revision 的全量默认：当无法判断目标产物时，Agent 会请用户明确要改 Doc、Slides 还是 Canvas，而不是重生成所有产物。

## 已覆盖测试

- 无 `修改：` 前缀的 Doc 编辑句会被解析为 `revise`。
- 用户在已有任务会话里说“在 Agent-Pilot 参赛方案中最后一行添加时间”时，只重生成 Doc。
- “修改：最后一行添加现在的时间...” 会推断为 Doc。
- “修改：更突出工程实现” 这类没有目标产物的模糊指令不会默认全量改三份产物，而是要求用户澄清。
- Router Agent 输出的结构化 `target_artifacts` 会被 Orchestrator 直接采用，避免二次关键词解析覆盖语义判断。

## 后续优化建议

下一步可以继续把 Router 的输入扩展到完整聊天上下文和飞书 artifact mention/link，让它不仅看当前文本，还能理解“这个材料”“刚才那个文档”等省略指代。

```json
{
  "intent": "revise",
  "target_artifacts": ["doc"],
  "operation": "append",
  "artifact_ref": "Agent-Pilot 参赛方案",
  "instruction": "最后一行添加现在的时间YY-MM-DD HH:MM"
}
```

这样可以进一步支持飞书富文本 mention、artifact 链接反查、跨轮省略目标，以及更细粒度的局部更新。
