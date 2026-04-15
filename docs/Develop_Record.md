## 2026-04-15 开发记录（Day 3）- 18:49:11

- 路由切换：将 `app/api/routers/task.py` 从 `run_mock_research` 调整为 `run_research`，正式走真实编排链路。
- 新增配置中心：`app/core/config.py` 新增 `Settings` 与 `get_settings()`（含 Tavily 参数、workspace 根目录和环境变量加载），用于统一管理搜索与运行时配置。
- 搜索服务重构：
  - `app/services/search_service.py` 保留 `mock` 版本并新增真实搜索链路，新增 `build_search_queries / dispatch_search / normalize_search_results / prepare_research_context / _extract_keywords / _persist_search_artifacts / run_web_research`。
  - 支持 `tavily` 接口调用、结果清洗去重、异常兜底、按分类组织来源。
  - 结果与上下文落盘到 `workspaces/tasks/<task_id>/`：`search_queries.json / search_results.json / raw_search.json / research_context.txt / sources_summary.md / search_results.md`。
- 报告构建链路：
  - `app/services/orchestration_service.py` 新建 `run_research`，串联 planning→search→report。
  - `app/services/report_service.py` 新增 `build_report`，按 `jd/company/interview` 分类生成报告段、来源概览与下一步动作。
  - `app/schemas/report.py` 搜索项新增 `category` 字段，便于分类聚合。
- 细节调整：`app/services/planner_service.py` 优化“输出差距分析与下一步准备动作”文案。
- 记录清理：` .gitignore` 增加 `reference_docs/` 与 `workspace/`，避免开发产物误提交。

### 当天产出与结论
- 完成 Day 3 的真实搜索链路雏形（planning -> web search -> normalize -> context -> report）。
- 本地上下文解析仍为 Day4 占位说明。
- 下一步：对接真实 job 描述本地资料处理、query 模板迭代、rerank 与流式上下文返回。
