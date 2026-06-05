export interface Health {
  status: string; llm_provider: string; vault: string; timestamp: string;
}
export interface Watcher {
  running: boolean; pid: number | null; started_at: string | null; exit_code: number | null;
}
export interface Llm {
  provider: string; label: string; anthropic_model: string; ollama_model: string;
  anthropic_key_set: boolean; valid_providers: string[];
}
export interface MeetingSummary {
  id: string; title: string; created: string; duration: string;
  task_count: number; participants: string; source_file: string;
  meeting_type: string; purpose: string;
}
export interface MeetingTask { done: boolean; description: string; }
export interface MeetingDetail {
  id: string; title: string; meta: Record<string, string>;
  resumo_md: string; tasks: MeetingTask[]; transcricao_md: string;
}
export interface Task {
  task_id: string; meeting_id: string; column: string; description: string;
  done: boolean; assignee: string; priority: string; due_date: string; timestamp: string;
}
export interface Steps { summary: boolean; note: boolean; kanban: boolean; wiki: boolean; }
export interface JobProgress {
  file: string; status: string;
  stage_number: number; stage_total: number; stage_label: string;
  stage_percent: number; percent: number; detail: string;
}
export interface StatusResponse { watcher_alive: boolean; active: JobProgress[]; }
export interface Config { watch_dir: string; steps: Steps; }
