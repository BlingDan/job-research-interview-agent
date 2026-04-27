from __future__ import annotations

from app.schemas.agent_pilot import AgentPilotTask, ArtifactBrief
from app.services.artifact_brief_builder import build_artifact_brief


def build_canvas_artifact(task: AgentPilotTask) -> str:
    return build_fallback_canvas(task)


def build_fallback_canvas(task: AgentPilotTask) -> str:
    brief = _brief(task)
    must_have = "<br/>".join(brief.must_have_points[:3])
    return f"""flowchart LR
    subgraph A["A-F: IM Intent Entry"]
        IM["Feishu IM / Lark IM<br/>Desktop + Mobile"]
        Parser["TaskMessageService<br/>command + context binding"]
    end

    subgraph B["B: Agent Planning"]
        Planner["Planner Agent<br/>intent, steps, tool choice"]
        Brief["ArtifactBrief<br/>one source for Doc, Slides, Canvas"]
    end

    subgraph Tools["MCP Tool Layer + lark-cli Bridge"]
        MCP["MCP Tool Layer<br/>Agent-facing tool protocol"]
        CLI["lark-cli Adapter<br/>stable Feishu execution"]
        Fake["Fake fallback<br/>demo continuity"]
    end

    subgraph C["C: Doc and Whiteboard"]
        Doc["Feishu Doc<br/>competition proposal"]
        Canvas["Feishu Canvas / Whiteboard<br/>architecture diagram"]
    end

    subgraph D["D: Presentation"]
        Slides["Feishu Slides<br/>5-page defense deck"]
    end

    subgraph EF["E-F: Collaboration and Delivery"]
        State["StateService<br/>progress, revision, artifacts"]
        Delivery["Final IM Delivery<br/>links + next actions"]
    end

    IM --> Parser --> Planner --> Brief --> MCP
    MCP --> CLI
    MCP -. unsupported .-> CLI
    CLI -. permission blocked .-> Fake
    CLI --> Doc
    CLI --> Slides
    CLI --> Canvas
    Fake --> Doc
    Fake --> Slides
    Fake --> Canvas
    Doc --> State
    Slides --> State
    Canvas --> State
    State --> Delivery --> IM

    Judge["Winning proof points<br/>{must_have}"]
    Brief --> Judge
"""


def _brief(task: AgentPilotTask) -> ArtifactBrief:
    return task.artifact_brief or build_artifact_brief(task)
