export type ActionType = "confirm" | "revise" | "reset" | "retry" | "clarify";

export interface TaskAction {
  type: ActionType;
  label: string;
  task_id: string;
  description: string;
  endpoint: string;
}

export interface TaskArtifact {
  artifact_id: string;
  kind: "doc" | "slides" | "canvas";
  title: string;
  status: string;
  url?: string | null;
  summary: string;
  local_path?: string | null;
  metadata: Record<string, unknown>;
}

export interface TaskSummary {
  task_id: string;
  input_text: string;
  status: string;
  summary?: string | null;
  artifacts: TaskArtifact[];
  actions: TaskAction[];
  created_at: string;
  updated_at: string;
}

export interface PlanStep {
  id: string;
  title: string;
  goal: string;
  agent: string;
  tool: string;
  expected_artifact?: string | null;
}

export interface AgentPlan {
  summary: string;
  confirmation_prompt?: string;
  steps: PlanStep[];
}

export interface RevisionRecord {
  revision_id: string;
  instruction: string;
  target_artifacts: string[];
  summary: string;
  change_detail: string;
  created_at: string;
}

export interface ToolExecutionRecord {
  call_id: string;
  adapter: string;
  status: string;
  started_at?: string | null;
  finished_at?: string | null;
  error?: string | null;
}

export interface TaskDetail {
  task_id: string;
  status: string;
  plan?: AgentPlan | null;
  artifact_brief?: Record<string, unknown> | null;
  artifacts: TaskArtifact[];
  tool_executions: ToolExecutionRecord[];
  revisions: RevisionRecord[];
  reply: string;
  error?: string | null;
}

export interface ArtifactPreview {
  task_id: string;
  kind: "doc" | "slides" | "canvas";
  title: string;
  url?: string | null;
  status: string;
  summary: string;
  content: string;
}
