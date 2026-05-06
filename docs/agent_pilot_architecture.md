# Agent-Pilot Architecture

## 1. 产品定位

`Agent-Pilot` 是一个以 `IM` 为规定入口、以统一助手为主驾驶、以 `Windows + Android` 为真实产品端、以 `Web cockpit` 为内部操盘面的多端办公协同骨架。

这个定位同时满足两类上位约束：

- 参赛要求中的 `IM 入口`、`多端同步`、`Agent 主驾驶`
- 产品演进上对 `Agent OS` 的理解：聊天不是终局，状态化任务系统才是中枢

## 2. 端角色边界

### IM

- 任务发起
- 轻量确认
- 进度查询
- 修订请求
- 关键提醒回流

### Web cockpit

- 任务总览
- 单任务观察
- 产物预览
- 待确认动作观察
- 有限人工干预

`cockpit` 不是普通用户主端，也不替代 IM。

### Windows

- 桌面常驻视角
- 高密度状态总览
- 快速动作入口
- 为未来托盘、本地文件、剪贴板接入预留边界

### Android

- 轻量任务追踪
- 待确认和待澄清
- 里程碑提醒
- 随身推进而非重编辑

## 3. 代码分层

```text
app/
  assistant/
    orchestrator.py
    runtime.py
  shared/
    models.py
    snapshots.py
    event_bus.py
    state_service.py
  surfaces/
    im/
    assistant/
    cockpit/
    windows/
    mobile/
  integrations/
    feishu/
    artifacts/
```

### `app/assistant`

统一助手层，负责：

- 创建任务
- 任务确认与执行
- 任务修订
- 统一工具层调度
- 将同一任务延续到不同 surface

### `app/shared`

共享任务状态层，负责：

- 统一任务实体与快照
- 事件流广播
- SQLite 状态持久化封装
- 各端共用动作定义

### `app/surfaces/*`

每个 surface 都只承担自己的入口和视图职责，不再自己维护一套任务模型。

### `app/integrations/*`

保留 Feishu/Lark 与产物工具层的实现，但将其降级为适配层，而不是产品中心。

## 4. 统一状态模型

核心共享类型定义在 [app/shared/models.py](E:\codespace\job-research-interview-agent\app\shared\models.py)：

- `TaskAggregate`
- `TaskStep`
- `TaskArtifact`
- `TaskAction`
- `TaskEvent`
- `SurfaceSnapshot`

任务状态统一为：

- `created`
- `planning`
- `waiting_user`
- `running`
- `delivering`
- `done`
- `revising`
- `failed`
- `archived`

步骤状态统一为：

- `pending`
- `running`
- `waiting_input`
- `done`
- `failed`
- `skipped`

动作类型统一为：

- `confirm`
- `revise`
- `reset`
- `retry`
- `clarify`

## 5. 同步策略

本轮优先级不是富文本实时协同，而是“任务状态一致”。

具体做法：

- 所有端都读取同一 `task_id`
- 状态快照由同一 SQLite 状态服务提供
- 变化通过 `event_bus` 向 cockpit websocket 广播
- Windows/Mobile 共享同一动作协议，不复制动作定义

这保证了后续扩展移动端和桌面端时，不会长出独立状态机。

## 6. 接口约定

### IM surface

- `POST /api/im/commands`
- `POST /api/im/events`

### Assistant surface

- `GET /api/assistant/tasks/{task_id}`
- `POST /api/assistant/tasks/{task_id}/actions/confirm`
- `POST /api/assistant/tasks/{task_id}/actions/revise`
- `POST /api/assistant/tasks/{task_id}/actions/reset`

### Cockpit surface

- `GET /api/cockpit/tasks`
- `GET /api/cockpit/tasks/{task_id}`
- `GET /api/cockpit/tasks/{task_id}/artifacts/{kind}`
- `WS /api/cockpit/ws/tasks`
- `WS /api/cockpit/ws/tasks/{task_id}`

### Windows / Mobile surface

- `GET /api/windows/home`
- `GET /api/windows/tasks/{task_id}`
- `GET /api/mobile/home`
- `GET /api/mobile/tasks/{task_id}`

## 7. 主流框架选择

### 后端

- `FastAPI`

原因：

- 当前后端已基于 FastAPI
- 便于快速收口为清晰 API surface
- 适合 websocket、Pydantic schema、快速演示

### Web cockpit

- `React + Vite`

原因：

- 主流、上手快、构建快
- 很适合做内部控制台和数据密集型视图
- 便于与 websocket 和 REST 契约对接

### Windows + Android

- `Flutter`

原因：

- 同一代码骨架即可覆盖 Windows 与 Android
- 适合较快落地真实产品端原型
- 能把多端同步的产品判断体现在同一工程里

## 8. 当前完成度

已完成：

- 后端按产品面重组
- 新路由命名落地
- 旧 `job-research` 主链路移出
- React cockpit 源码骨架初始化
- Flutter 多端源代码骨架初始化

本轮明确不做：

- 富文本实时冲突合并
- Windows 托盘与本地文件深集成
- Android 推送通知完善
- Web 成为普通用户主端
