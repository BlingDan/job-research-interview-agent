import json
from pathlib import Path

from app.core.config import get_settings
from app.schemas.state import ResearchState
from app.schemas.task import TaskCreateRequest
from app.services.planner_service import build_planning
from app.services.report_service import build_report, render_report_markdown
from app.services.search_service import run_task_search
from app.services.summarizer_service import build_task_summary
from app.services.rag_service import ingest_local_document
from app.tools.retriever_tool import get_doc_type_filter, get_local_context

class ResearchCoordinator:
    def __init__(self, task_id: str, payload: TaskCreateRequest):
        self.task_id = task_id
        self.payload = payload
        self.settings = get_settings()
        self.task_dir = Path(self.settings.workspace_root) / "tasks" / task_id
        self.task_dir.mkdir(parents=True, exist_ok=True)
        self.state = ResearchState(task_id=task_id, input=payload)

    def run(self) -> ResearchState:
        try:
            self.plan()
            self.build_local_knowledge()
            self.execute_tasks()
            self.build_final_report()
        except Exception as exc:
            self.state.status = "failed"
            self.state.error = str(exc)
            raise
        finally:
            self.persist_status()

        return self.state

    def plan(self) -> None:
        self.state.status = "planning"
        self.state.planning = build_planning(self.payload)
        self._write_json("planning.json", [item.model_dump() for item in self.state.planning])

    def build_local_knowledge(self) -> None:
        local_path = (self.payload.local_context_path or "").strip()

        if not local_path:
            return
        
        ingest_local_document(
            local_path,
            doc_type="other",
            original_filename=Path(local_path).name,
        )


    def execute_tasks(self) -> None:
        self.state.status = "executing"

        for todo in self.state.planning:
            todo.status = "running"

            results, _, _ = run_task_search(
                task_id=self.task_id,
                todo=todo,
                payload=self.payload,
            )

            local_bundle = get_local_context(
                todo.query,
                doc_types=get_doc_type_filter(todo.category)
            )
            self.state.local_context = self._merge_local_context(
                self.state.local_context,
                local_bundle.summary,
            )

            summary = build_task_summary(
                task_id=self.task_id,
                todo=todo,
                results=results,
                task_dir=self.task_dir,
                local_context=local_bundle.summary,
            )

            todo.status = "completed"
            todo.sources = summary.sources
            todo.summary_path = summary.summary_path

            self.state.task_summaries.append(summary)
            self.state.search_results.extend(results)

    def build_final_report(self) -> None:
        self.state.status = "reporting"
        report = build_report(self.state)
        self.state.report = report
        self._write_json("report.json", report.model_dump())
        self._write_text("report.md", render_report_markdown(report))
        self.state.status = "done"

    def persist_status(self) -> None:
        self._write_json("state.json", self.state.model_dump())
    
    def _merge_local_context(self, current: str | None, new_value: str | None) -> str | None:
        """合并新的本地知识摘要到现有的 local_context 字段中，去重并用换行分隔。
         - current: 当前已有的 local_context 内容
         - new_value: 新的本地知识摘要内容
        """
        values = [item.strip() for item in [current or "", new_value or ""] if item and item.strip()]
        if not values:
            return None

        deduped: list[str] = []
        for item in values:
            if item not in deduped:
                deduped.append(item)
        return "\n\n".join(deduped)
        
    def _write_json(self, filename: str, data) -> None:
        (self.task_dir / filename).write_text(
            json.dumps(data, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

    def _write_text(self, filename: str, content: str) -> None:
        (self.task_dir / filename).write_text(content, encoding="utf-8")
    
    