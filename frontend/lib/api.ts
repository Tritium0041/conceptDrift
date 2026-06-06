export const API_BASE_URL =
  process.env.NEXT_PUBLIC_API_BASE_URL?.replace(/\/$/, "") ?? "http://127.0.0.1:8000";

export type TaskStatus = "pending" | "running" | "succeeded" | "failed";
export type TaskMode = "guided" | "yolo";

export type Task = {
  id: string;
  direction: string;
  sources: string[];
  depth: string;
  mode: TaskMode;
  status: TaskStatus;
  progress: number;
  stage: string;
  error: string | null;
  report_id: number | null;
  created_at: string;
  updated_at: string;
};

export type SourceItem = {
  id: number;
  source: string;
  title: string;
  url: string;
  summary: string;
  signal_score: number;
};

export type Report = {
  id: number;
  title: string;
  summary: string;
  markdown: string;
  scores: Record<string, number>;
  tags: string[];
  archived: boolean;
  sources: SourceItem[];
  created_at: string;
  updated_at: string;
};

export type ReportListItem = Omit<Report, "markdown" | "sources">;

export type ReportList = {
  items: ReportListItem[];
  total: number;
  limit: number;
  offset: number;
};

export type Health = {
  status: string;
  provider: string;
  database: string;
};

export type TaskList = {
  items: Task[];
  total: number;
  limit: number;
  offset: number;
};

export type ProviderName = "mock" | "codex" | "response";

export type AppConfig = {
  agent_provider: ProviderName;
  openai_api_key_configured: boolean;
  openai_api_key_masked: string | null;
  openai_base_url: string;
  openai_model: string;
  openai_timeout_seconds: number;
  openai_tracing_disabled: boolean;
  codex_agent_timeout_seconds: number;
  codex_agent_network_enabled: boolean;
  codex_agent_web_search_mode: string;
};

export type AppConfigUpdate = Omit<AppConfig, "openai_api_key_configured" | "openai_api_key_masked"> & {
  openai_api_key?: string;
  clear_openai_api_key: boolean;
};

export async function apiFetch<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(`${API_BASE_URL}${path}`, {
    ...init,
    headers: {
      "Content-Type": "application/json",
      ...init?.headers
    }
  });
  if (!response.ok) {
    const detail = await response.text();
    throw new Error(detail || `Request failed: ${response.status}`);
  }
  return (await response.json()) as T;
}

export function resumeTask(taskId: string) {
  return apiFetch<Task>(`/api/tasks/${taskId}/resume`, { method: "POST" });
}

export function exportUrl(reportId: number, format: "markdown" | "pdf") {
  return `${API_BASE_URL}/api/reports/${reportId}/export?format=${format}`;
}

export function taskEventsUrl(taskId: string) {
  return `${API_BASE_URL}/api/tasks/${taskId}/events`;
}
