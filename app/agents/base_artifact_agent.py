from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Generic, TypeVar

from app.core.config import get_settings
from app.core.logging import get_logger
from app.schemas.agent_pilot import AgentPilotTask, ArtifactBrief
from app.services.artifact_brief_builder import build_artifact_brief

T = TypeVar("T")

logger = get_logger()


class BaseArtifactAgent(ABC, Generic[T]):
    """Template-method base for Doc/Canvas/Slides agents.

    Subclasses override _build_llm, _validate, _build_fallback, and
    _agent_name.  Callers use build(task) — the base class handles
    logging and the try/LLM → fallback flow.
    """

    @property
    @abstractmethod
    def _agent_name(self) -> str: ...

    @abstractmethod
    def _build_llm(self, task: AgentPilotTask, brief: ArtifactBrief) -> T: ...

    @abstractmethod
    def _validate(self, result: T) -> bool: ...

    @abstractmethod
    def _build_fallback(self, task: AgentPilotTask, brief: ArtifactBrief) -> T: ...

    def build(self, task: AgentPilotTask) -> T:
        settings = get_settings()
        artifact_mode = settings.lark_artifact_mode or settings.lark_mode
        if artifact_mode in {"fake", "dry_run"}:
            logger.info(
                "%s using fallback artifact generation (task_id=%s, artifact_mode=%s).",
                self._agent_name,
                task.task_id,
                artifact_mode,
            )
            return self._build_fallback(task, self._brief(task))
        try:
            result = self._build_llm(task, self._brief(task))
            if self._validate(result):
                return result
            logger.warning(
                "%s LLM result failed validation (task_id=%s). Falling back.",
                self._agent_name,
                task.task_id,
            )
        except Exception:
            logger.warning(
                "%s LLM call failed (task_id=%s). Falling back.",
                self._agent_name,
                task.task_id,
                exc_info=True,
            )
        return self._build_fallback(task, self._brief(task))

    @staticmethod
    def _brief(task: AgentPilotTask) -> ArtifactBrief:
        return task.artifact_brief or build_artifact_brief(task)
