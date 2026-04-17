from __future__ import annotations

import json
from pathlib import Path

from app.core.config import get_settings
from app.schemas.event import ResearchEvent
from app.schemas.state import ResearchState, TodoItem, TaskSummary
from app.schemas.report import PlanningItem
from app.schemas.task import TaskCreateRequest
from app.services.search_service import run_web_research


class ResearchCoordinator:
    def __init__(self, task_id: str, payload: TaskCreateRequest):
        self.task_id = task_id
        self.payload = payload
        self.settings = get_settings()
        self.task_dir = Path(self.settings.workspace_root)/"tasks"/task_id
        self.state = ResearchState(task_id=task_id, input=payload)
    
    def run(self) -> ResearchState:
        self.plan()
        self.execute_task
        self.build_final_report
        self.persist_status()

        return self.state
        

    def plan(self) -> None:
        self.state.status = "planning"

        # TODO 真正的 LLM 调用
        self.state.planning = [
            TodoItem(
                id="todo-1",
                title="JD 关键能力拆解",
                intent="提取岗位高频技能与核心要求",
                query=self.payload.jd_text[:80],
            ),
            TodoItem(
                id="todo-2",
                title="公司与业务背景调研",
                intent="梳理公司业务、技术栈与团队可能关注点",
                query=self.payload.company_name or "目标公司 业务 技术栈",
            ),
            TodoItem(
                id="todo-3",
                title="面试主题准备",
                intent="整理该岗位可能出现的高频面试点",
                query=self.payload.interview_topic or "岗位 高频面试问题",
            ),
        ]

        self._write_json("planning.json", [item.model_dump() for item in self.state.planning])

    def execute_task(self) -> None:
        self.state.status = "executing"
        all_result = []

        # Why start from 1? Because the planning step is more like a "table of contents" for the report, and the actual research tasks start from step 1. This way, the report can directly use the step number to reference the corresponding research task without needing to adjust for an offset. It keeps the numbering intuitive and aligned with the actual tasks being executed.
        for index, todo in enumerate(self.state.planning, start=1):
            todo.status = "running"

            planning_item = PlanningItem(
                step=index,
                title=todo.title,
                objective=todo.intent,
            )

            results, _, _ = run_web_research(
                task_id=self.task_id,
                payload=self.payload,
                planning=[planning_item],
            )

            todo.status = "completed"
            todo.sources = [item.source for item in results]
            all_result.extend(results)


            raw_path = f"task_{index}_search.json"
            self._write_json(raw_path, [item.model_dump() for item in results])
            
            summary_text = self._build_summary_text(todo, results)
            summary_path = f"task_{index}_summary.md"
            self._write_text(summary_path, summary_text)
            todo.summary_path = str(self.task_dir/summary_path)

            self.state.task_summaries.append(
                TaskSummary(
                    todo_id=todo.id,
                    title=todo.title,
                    summary=summary_text,
                    sources=todo.sources,
                    raw_search_path=str(self.task_dir/raw_path),
                    summary_path=str(self.task_dir/summary_path),
                )
            )
        
        self.state.search_results = all_result
        # self.state.status = "completed"
    
    def build_final_report(self) -> None:
        self.state.status = "reporting"

        # TODO LLM 生成最终报告
        from app.schemas.report import ReportPayload, ReportSection

        sections = []
        for item in self.state.task_summaries:
            sections.append(
                ReportSection(
                    title=item.title,
                    bullets=[item.summary[:120]],
                )
            )

        self.state.report = ReportPayload(
            title="面试准备研究报告",
            summary="已按规划、执行、汇总三阶段完成研究流程。",
            sections=sections,
            next_actions=[
                "补充更细的岗位技术映射",
                "补充本地资料与候选人项目经验对应关系",
            ],
        )

        report_md = "# 面试准备研究报告\n\n"
        report_md += self.state.report.summary + "\n\n"
        for section in self.state.report.sections:
            report_md += f"## {section.title}\n"
            for bullet in section.bullets:
                report_md += f"- {bullet}\n"
            report_md += "\n"

        self._write_text("report.md", report_md)
        self.state.status = "done"

    def persist_status(self) -> None:
        self._write_json("state.json", self.state.model_dump())

    def _build_summary_text(self, todo: TodoItem, results) -> str:
        lines = [f"## 任务：{todo.title}", ""]
        lines.append(f"目标：{todo.intent}")
        lines.append("")
        lines.append("### 关键结果")
        for item in results[:5]:
            lines.append(f"- {item.title} | {item.source}")
        return "\n".join(lines)


    def _write_json (self, filename: str, data) -> None:
        (self.task_dir / filename).write_text(
            json.dumps(data, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
    
    def _write_text(self, filename: str, content: str) -> None:
        (self.task_dir/filename).write_text(content, encoding="utf-8")
