# Agent-Pilot Demo Guide

## 1. Demo 目标

本轮演示的重点不是“某个单端 UI 很完整”，而是证明下面这条主链路成立：

```text
IM -> unified assistant -> task state -> cockpit -> Windows / Android shell
```

演示时应强调：

- `IM` 是规定入口
- 统一助手主导任务推进
- `cockpit` 是观察与操盘面
- `Windows / Android` 消费同一任务状态，而不是两套模型

## 2. 启动后端

```powershell
.venv\Scripts\python.exe -m uvicorn app.main:app --reload
```

默认入口：

- API Root: `http://127.0.0.1:8000`
- Cockpit static: `http://127.0.0.1:8000/static`

## 3. 启动 React cockpit

```powershell
Set-Location clients\agent_pilot_cockpit
bun install
bun run dev
```

默认地址：

- `http://127.0.0.1:5173`

构建静态产物：

```powershell
bun run build
```

构建后，后端根路径会优先托管 `dist` 目录。

## 4. 启动 Flutter 骨架

```powershell
Set-Location clients\agent_pilot_flutter
flutter pub get
flutter run -d windows
```

Android：

```powershell
flutter run -d android
```

如果当前机器没有安装 Flutter，本轮也可以先通过源码骨架和 API 契约完成评审说明。

## 5. 触发任务

通过 IM 命令接口创建任务：

```powershell
$payload = @{
  message = "Create an office collaboration package with doc, slides, and canvas"
  chat_id = "oc_demo"
  message_id = "om_demo"
  user_id = "ou_demo"
} | ConvertTo-Json

Invoke-RestMethod `
  -Method Post `
  -Uri http://127.0.0.1:8000/api/im/commands `
  -ContentType "application/json" `
  -Body $payload
```

预期：

- 返回 `WAITING_CONFIRMATION`
- cockpit 任务列表出现同一 `task_id`
- Windows / Android 首页能看到相同任务摘要

## 6. 确认任务

```powershell
Invoke-RestMethod `
  -Method Post `
  -Uri "http://127.0.0.1:8000/api/assistant/tasks/<task_id>/actions/confirm"
```

预期：

- 状态进入 `DONE`
- 生成 `doc / slides / canvas` 三类产物
- cockpit 可查看详情与产物预览
- Windows / Android 待确认动作消失或减少

## 7. 修订任务

```powershell
$payload = @{ instruction = "Revise slides to emphasize engineering implementation and cross-device sync" } | ConvertTo-Json

Invoke-RestMethod `
  -Method Post `
  -Uri "http://127.0.0.1:8000/api/assistant/tasks/<task_id>/actions/revise" `
  -ContentType "application/json" `
  -Body $payload
```

预期：

- 修订记录挂到同一 `task_id`
- cockpit 时间线能看到 revision
- 相关 artifact 更新

## 8. 演示顺序建议

1. 先在 IM 入口创建任务
2. 打开 cockpit，看任务进入列表
3. 在 cockpit 里观察计划、步骤、产物
4. 执行确认动作，让产物生成完成
5. 打开 Windows / Android 骨架，展示它们消费的是同一任务状态
6. 发起一条修订，再回到 cockpit 看时间线变化

## 9. 评审讲法

可以这样讲：

- “我们保留 IM 作为规定入口，不偏离赛题要求。”
- “我们没有把产品停留在飞书聊天窗口，而是把任务状态抽成统一中枢。”
- “Web cockpit 负责管理和演示，Windows 与 Android 是真实用户端骨架。”
- “所以多端不是复制界面，而是共享任务状态、按端分工。”
