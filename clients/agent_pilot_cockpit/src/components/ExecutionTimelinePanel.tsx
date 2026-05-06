import type { AgentPlan, RevisionRecord, ToolExecutionRecord } from "../types";

interface ExecutionTimelinePanelProps {
  plan?: AgentPlan | null;
  toolExecutions: ToolExecutionRecord[];
  revisions: RevisionRecord[];
}

export function ExecutionTimelinePanel({
  plan,
  toolExecutions,
  revisions,
}: ExecutionTimelinePanelProps) {
  return (
    <section className="panel">
      <div className="panel-header">
        <div>
          <p className="eyebrow">Execution</p>
          <h3>Timeline</h3>
        </div>
      </div>
      <div className="timeline-grid">
        <div>
          <h4>Plan Steps</h4>
          <ul className="timeline-list">
            {plan?.steps?.map((step) => (
              <li key={step.id}>
                <strong>{step.title}</strong>
                <span>{step.agent} via {step.tool}</span>
              </li>
            )) || <li><span>No plan steps yet.</span></li>}
          </ul>
        </div>
        <div>
          <h4>Tool Runs</h4>
          <ul className="timeline-list">
            {toolExecutions.length ? toolExecutions.map((item) => (
              <li key={item.call_id}>
                <strong>{item.adapter}</strong>
                <span>{item.status}</span>
              </li>
            )) : <li><span>No tool execution records yet.</span></li>}
          </ul>
        </div>
        <div>
          <h4>Revisions</h4>
          <ul className="timeline-list">
            {revisions.length ? revisions.map((item) => (
              <li key={item.revision_id}>
                <strong>{item.instruction}</strong>
                <span>{new Date(item.created_at).toLocaleString()}</span>
              </li>
            )) : <li><span>No revisions yet.</span></li>}
          </ul>
        </div>
      </div>
    </section>
  );
}
