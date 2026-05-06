from __future__ import annotations

import json

from app.agents.base_artifact_agent import BaseArtifactAgent
from app.core.llm import JobResearchLLM
from app.schemas.agent_pilot import AgentPilotTask, ArtifactBrief


class CanvasAgent(BaseArtifactAgent[str]):
    _agent_name = "CanvasAgent"

    def _build_llm(self, task: AgentPilotTask, brief: ArtifactBrief) -> str:
        llm = JobResearchLLM(temperature=0.3, max_tokens=4096)
        messages = [
            {
                "role": "system",
                "content": "你是 Agent-Pilot 的 Canvas Agent。根据用户的原始需求和 ArtifactBrief 生成一个 Mermaid flowchart 架构图。展示 IM、Agent 编排、飞书办公套件联动、多端协同和 fallback 机制。只返回 Mermaid 代码，不要额外解释，不要用代码块包裹。",
            },
            {
                "role": "user",
                "content": f"""原始需求：
{task.input_text}

方案摘要：
{brief.task_summary}

Agent 架构：
{json.dumps(brief.agent_architecture, ensure_ascii=False)}

飞书套件联动：
{json.dumps(brief.feishu_suite_linkage, ensure_ascii=False)}

多端协同：
{json.dumps(brief.multi_end_collaboration_story, ensure_ascii=False)}

风险与 fallback：
{json.dumps(brief.risk_and_fallback_story, ensure_ascii=False)}

一致性约束（以下核心事实必须在画板中保持一致）：
{json.dumps(brief.consistency_anchors, ensure_ascii=False)}

请生成 Mermaid flowchart 架构图。""",
            },
        ]
        raw = llm.invoke(messages).strip()
        return _strip_mermaid_fence(raw)

    def _validate(self, result: str) -> bool:
        lower = result.lower()
        return "flowchart" in lower or "graph" in lower

    def _build_fallback(self, task: AgentPilotTask, brief: ArtifactBrief) -> str:
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
        Doc["Feishu Doc<br/>project proposal"]
        Canvas["Feishu Canvas / Whiteboard<br/>architecture diagram"]
    end

    subgraph D["D: Presentation"]
        Slides["Feishu Slides<br/>5-page presentation deck"]
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

    Capabilities["Key Capabilities<br/>{must_have}"]
    Brief --> Capabilities
"""


_canvas_agent = CanvasAgent()


def build_canvas_artifact(task: AgentPilotTask) -> str:
    return _canvas_agent.build(task)


def build_fallback_canvas(task: AgentPilotTask) -> str:
    return _canvas_agent._build_fallback(task, _canvas_agent._brief(task))


def _strip_mermaid_fence(text: str) -> str:
    stripped = text.strip()
    if stripped.startswith("```"):
        lines = stripped.split("\n")
        if lines and lines[0].startswith("```"):
            lines = lines[1:]
        if lines and lines[-1].startswith("```"):
            lines = lines[:-1]
        return "\n".join(lines)
    return stripped
