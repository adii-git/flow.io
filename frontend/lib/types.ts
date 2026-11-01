export type Project = { id: string; name: string };
export type TaskSummary = { id: string; title: string; status: string; project_id: string | null; created_at: string };
export type Subtask = {
  id: string; position: number; capability: string; label: string; description: string;
  tool_id: string | null; status: string; depends_on: string[];
  routing: { tool_id?: string; tool_name?: string; confidence?: number; reasons?: string[]; alternatives?: string[]; context_items?: number; skipped?: boolean; note?: string } | null;
  output_preview: string | null;
};
export type Task = {
  id: string; objective: string; status: string; project_id: string | null; created_at: string;
  plan: { source: string; title: string; task_type: string; requirements: string[]; capabilities: string[] } | null;
  context_count: number; tools_used: string[]; subtasks: Subtask[];
  error: { what: string; doing: string; details: string } | null;
};
export const STATUS_LABEL: Record<string, string> = { draft: "Outlined", planned: "Ready to run", running: "Running", done: "Complete", failed: "Needs attention" };
export const STEP_LABEL: Record<string, string> = { pending: "Waiting", planned: "Queued", running: "Running", done: "Done", failed: "Failed", skipped: "Skipped" };

export type Tool = {
  id: string; name: string; provider: string; summary: string; capabilities: string[]; context_window: number;
  supports_images: boolean; supports_files: boolean; supports_tools: boolean;
  cost_class: string; speed_class: string; requires_key: boolean; status: "ready" | "needs_key" | "planned";
};
export type Connection = { provider: string; key_hint: string; connected_at: string };
export const CAP_LABEL: Record<string, string> = {
  reasoning: "Reasoning", writing: "Writing", long_context_documents: "Long documents", web_research: "Web research", code_generation: "Code writing",
  code_execution: "Code running", image_generation: "Images", file_processing: "Files", validation: "Validation",
};
export const PROVIDER_LABEL: Record<string, string> = { gemini: "Google Gemini", groq: "Groq", huggingface: "Hugging Face", local: "Local / Open Source", anthropic: "Anthropic", brave: "Brave Search", openai: "OpenAI", conduit: "Built in", pollinations: "Pollinations (free)" };

export type TaskEvent = { id: number; type: string; message: string; subtask_id?: string; tool?: string; seq?: number };
export type PlanOut = { task: Task; blockers: { provider: string; tools: string[] }[]; notes: string[] };
export type FollowUp = { id: string; message: string; created_at: string };
export type ContextTransfer = {
  subtask_id: string; step: string | null; tool: string | null;
  sent: { item_id: string; kind: string; label: string; chars: number; trimmed: boolean; preview: string }[];
  withheld: { item_id: string; kind: string; label: string; reason: string }[];
};
export type ResultPayload = {
  kind: string; title: string; simulated: boolean; markdown: string;
  validation: { passed: boolean | null; issues: string[]; note?: string };
  sections: { label: string; capability: string; text: string }[];
  sources?: { title: string; url: string; description: string }[]; findings?: string;
  files?: { path: string; language: string; content: string }[];
  chart?: { title: string; labels: string[]; values: number[] } | null; insights?: string;
  images?: { mime?: string; b64?: string; url?: string }[];
};
