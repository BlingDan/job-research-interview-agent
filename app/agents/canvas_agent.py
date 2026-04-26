from __future__ import annotations

from app.schemas.agent_pilot import AgentPilotTask


def build_canvas_artifact(task: AgentPilotTask) -> str:
    return build_fallback_canvas(task)


def build_fallback_canvas(task: AgentPilotTask) -> str:
    return """flowchart LR
    IM[Feishu IM]
    Parser[TaskMessageService]
    Planner[Planner Agent]
    State[State Machine]
    Doc[Feishu Doc]
    Slides[Feishu Slides]
    Canvas[Canvas / Whiteboard]
    Delivery[Final IM Delivery]

    IM --> Parser --> Planner --> State
    State --> Doc
    State --> Slides
    State --> Canvas
    Doc --> Delivery
    Slides --> Delivery
    Canvas --> Delivery
    Delivery --> IM
"""

