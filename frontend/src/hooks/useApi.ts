import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { api } from "../api/client";
import type {
  Health, Watcher, Llm, MeetingSummary, MeetingDetail, Task, Steps,
} from "../api/types";

export const useHealth = () =>
  useQuery({
    queryKey: ["health"],
    queryFn: () => api.get<Health>("/api/health"),
    refetchInterval: 3000,
  });

export const useWatcher = () =>
  useQuery({
    queryKey: ["watcher"],
    queryFn: () => api.get<Watcher>("/api/watcher"),
    refetchInterval: 3000,
  });

export const useLlm = () =>
  useQuery({ queryKey: ["llm"], queryFn: () => api.get<Llm>("/api/llm") });

export const useMeetings = () =>
  useQuery({ queryKey: ["meetings"], queryFn: () => api.get<MeetingSummary[]>("/api/meetings") });

export const useMeeting = (id: string) =>
  useQuery({
    queryKey: ["meeting", id],
    queryFn: () => api.get<MeetingDetail>(`/api/meetings/${encodeURIComponent(id)}`),
    enabled: !!id,
  });

export const useTasks = () =>
  useQuery({ queryKey: ["tasks"], queryFn: () => api.get<Task[]>("/api/tasks") });

export function useWatcherControl() {
  const qc = useQueryClient();
  const invalidate = () => qc.invalidateQueries({ queryKey: ["watcher"] });
  return {
    start: useMutation({ mutationFn: () => api.post("/api/watcher/start"), onSuccess: invalidate }),
    stop: useMutation({ mutationFn: () => api.post("/api/watcher/stop"), onSuccess: invalidate }),
    restart: useMutation({ mutationFn: () => api.post("/api/watcher/restart"), onSuccess: invalidate }),
  };
}

export function useSetProvider() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (provider: string) => api.post("/api/llm/provider", { provider }),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["llm"] }),
  });
}

export function useSetSteps() {
  return useMutation({ mutationFn: (steps: Steps) => api.post("/api/config/steps", steps) });
}

export function useSetWatchDir() {
  return useMutation({ mutationFn: (watch_dir: string) => api.post("/api/config/watch-dir", { watch_dir }) });
}

export function useProcessFile() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (file: string) => api.post("/api/process", { file }),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["meetings"] }),
  });
}

export function useDeleteMeeting() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (id: string) => api.del(`/api/meetings/${encodeURIComponent(id)}`),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["meetings"] }),
  });
}

export function useMoveTask() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (v: { task_id: string; meeting_id: string; to_column: string }) =>
      api.post("/actions/tasks/move", v),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["tasks"] }),
  });
}
