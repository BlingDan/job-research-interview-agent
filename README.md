<div align="center">
  <img src="./assets/img/agent-pilot.png" alt="Agent-Pilot hero image" width="100%" />
  <h1>Agent-Pilot</h1>
  <h3>基于 IM 的办公协同智能助手</h3>
  <p><em>从飞书/Lark IM 对话到文档、汇报材料与画板的一键智能闭环</em></p>
  <p>
    <img src="https://img.shields.io/github/stars/BlingDan/job-research-interview-agent?style=flat&logo=github" alt="GitHub stars" />
    <img src="https://img.shields.io/github/forks/BlingDan/job-research-interview-agent?style=flat&logo=github" alt="GitHub forks" />
    <img src="https://img.shields.io/badge/platform-Feishu%20%2F%20Lark-3370ff?style=flat" alt="Feishu/Lark platform" />
    <img src="https://img.shields.io/badge/language-Chinese-brightgreen?style=flat" alt="Language" />
    <img src="https://img.shields.io/badge/backend-FastAPI-009688?style=flat&logo=fastapi" alt="FastAPI" />
  </p>
</div>

## 项目简介

Agent-Pilot 是面向飞书/Lark 的办公协同智能助手，围绕飞书/Lark IM 的核心交互场景展开。用户在 IM 中提出目标，Agent 理解任务、规划步骤、生成办公产物，并把结果回传到同一个会话。

当前这轮重构围绕参赛要求中的 `IM 入口`、`多端同步` 和 `Agent 主驾驶` 继续收口。仓库主线已经从旧研究项目语义切换到新的 `Agent-Pilot` 骨架：`IM` 负责入口，`Web cockpit` 负责观察与有限干预，`Windows + Android` 作为真实产品端骨架，共享同一任务状态。

核心链路：

```text
Feishu / Lark IM
-> Agent 意图捕获
-> 任务理解与计划
-> 文档 / 幻灯片 / 画板生成
-> 同一任务状态跨端同步
-> IM 会话交付与后续修改
```

## 核心能力

- **IM 原生入口**：支持群聊或私聊中的自然语言任务发起。
- **Agent 任务规划**：Planner Agent 将目标拆解为可执行步骤和工具调用计划。
- **办公套件联动**：生成飞书 Doc、Slides、Canvas/Whiteboard 等交付物。
- **多端协同体验**：IM、cockpit、Windows、Android 围绕同一任务状态协同。
- **进度与修改闭环**：支持 `当前进度`、`确认`、`修改：...`、`/reset` 等交互。
- **演示稳定性**：官方 MCP、`lark-cli`、fake artifact 多层 fallback，保障演示和实际使用的稳定性。

## 功能场景

| 场景 | 场景说明 | Agent-Pilot 对应实现 |
| --- | --- | --- |
| A | 意图 / 指令入口 | 飞书 IM 消息触发 Agent-Pilot 任务 |
| B | 任务理解和规划 | Planner Agent 生成执行计划与 ToolPlan |
| C | 文档 / 白板生成 | DocAgent 与 CanvasAgent 生成方案文档和架构画板 |
| D | 汇报材料生成 | PresentationAgent 生成 5 页项目汇报 Slides |
| E | 多端协同 | 同一 `task_id` 在 IM、cockpit、Windows、Android 间连续推进 |
| F | 总结与交付 | DeliveryService 将最终成果回传到同一 IM 会话 |

## 当前骨架进展

- 后端：`FastAPI`，按 `assistant / shared / surfaces / integrations` 重组。
- cockpit：`React + Vite` 工程已初始化，接入新的 `/api/cockpit/*` 与 websocket 契约。
- 真实端：`Flutter` 工程骨架已初始化，覆盖 `Windows + Android` 的共享状态模型。
- IM：保留 Feishu/Lark 入口与适配器，但上层语义提升为 `IM-first`，不再把飞书当唯一 UI。
- 旧研究域：`task / report / search / summarizer / rag` 主链路已移出，仓库主线只保留 `Agent-Pilot` 语义。

## 仓库结构

```text
app/
  assistant/            Unified assistant runtime and orchestration
  shared/               Shared task models, snapshots, event bus, persistence wrappers
  surfaces/
    im/                 IM command and event ingress
    assistant/          Assistant task actions
    cockpit/            Web cockpit query and websocket surface
    windows/            Windows surface API
    mobile/             Mobile surface API
  integrations/
    feishu/             Feishu/Lark adapter exports
    artifacts/          Artifact fallback and tool-layer exports
clients/
  agent_pilot_cockpit/  React + Vite cockpit
  agent_pilot_flutter/  Flutter shell for Windows + Android
docs/
  agent_pilot_architecture.md
  agent_pilot_demo.md
```

## 主要接口

- `POST /api/im/commands`
- `POST /api/im/events`
- `GET /api/assistant/tasks/{task_id}`
- `POST /api/assistant/tasks/{task_id}/actions/confirm`
- `POST /api/assistant/tasks/{task_id}/actions/revise`
- `POST /api/assistant/tasks/{task_id}/actions/reset`
- `GET /api/cockpit/tasks`
- `GET /api/cockpit/tasks/{task_id}`
- `GET /api/cockpit/tasks/{task_id}/artifacts/{kind}`
- `WS /api/cockpit/ws/tasks`
- `WS /api/cockpit/ws/tasks/{task_id}`
- `GET /api/windows/home`
- `GET /api/windows/tasks/{task_id}`
- `GET /api/mobile/home`
- `GET /api/mobile/tasks/{task_id}`

## 快速开始

```bash
uv run pytest
uv run uvicorn app.main:app --reload
```

启动飞书 IM 事件监听：

```bash
uv run python scripts/lark_event_listener.py
```

启动 cockpit：

```bash
cd clients/agent_pilot_cockpit
bun install
bun run dev
```

如果已经构建过静态产物，也可以直接访问后端根路径；`app.main` 会优先托管 `clients/agent_pilot_cockpit/dist`。

Flutter 骨架：

```bash
cd clients/agent_pilot_flutter
flutter pub get
flutter run -d windows
```

如果本机没有安装 Flutter，当前仓库仍然保留完整骨架与共享 API 契约，可在安装 Flutter 后直接接续。

推荐演示口令：

```text
@Agent 帮我生成一份产品方案文档和 5 页项目汇报材料。重点突出 Agent 编排、多端协同、飞书办公套件联动和工程实现。
```

## 技术栈

- Python / FastAPI
- React + Vite
- Flutter
- Feishu/Lark `lark-cli`
- Official Feishu MCP Tool Layer
- OpenAI-compatible LLM endpoint
- pytest

## 文档

- [演示与运行指南](./docs/agent_pilot_demo.md)
- [架构文档](./docs/agent_pilot_architecture.md)
- [重构设计文档](./docs/superpowers/specs/2026-04-26-agent-pilot-refactor-design.md)
- [Feishu MCP Tool Layer 设计](./docs/superpowers/specs/2026-04-27-feishu-mcp-tool-layer-design.md)

## 实现原则

- `IM` 是规定入口，不被网页端替代。
- `Web cockpit` 是操盘面，不升级成普通用户主端。
- `Windows + Android` 走“共享骨架 + 端差异”路线。
- 优先保证任务状态一致，再扩展复杂内容协同。
- 优先采用主流框架：`FastAPI`、`React + Vite`、`Flutter`。
