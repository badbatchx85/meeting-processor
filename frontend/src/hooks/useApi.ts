import { useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { api, uploadFile } from "../api/client";
import type {
  Health, Watcher, Llm, MeetingSummary, MeetingDetail, Task, Steps, StatusResponse, Config,
  HistoryEntry, LocalModels, PullStatus, GenerationLogEntry, SourceInfo,
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

export const useStatus = () =>
  useQuery({
    queryKey: ["status"],
    queryFn: () => api.get<StatusResponse>("/api/status"),
    refetchInterval: 2000,
  });

export const useLlm = () =>
  useQuery({ queryKey: ["llm"], queryFn: () => api.get<Llm>("/api/llm") });

export const useConfig = () =>
  useQuery({ queryKey: ["config"], queryFn: () => api.get<Config>("/api/config") });

export const useMeetings = () =>
  useQuery({ queryKey: ["meetings"], queryFn: () => api.get<MeetingSummary[]>("/api/meetings") });

export const useHistory = () =>
  useQuery({ queryKey: ["history"], queryFn: () => api.get<HistoryEntry[]>("/api/history") });

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

export const useLocalModels = (enabled: boolean) =>
  useQuery({
    queryKey: ["local-models"],
    queryFn: () => api.get<LocalModels>("/api/llm/local-models"),
    enabled,
  });

export const usePullStatus = (enabled: boolean) =>
  useQuery({
    queryKey: ["pull-status"],
    queryFn: () => api.get<PullStatus>("/api/llm/local-models/pull/status"),
    enabled,
    refetchInterval: 1000,
  });

export function usePullModel() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (model: string) => api.post("/api/llm/local-models/pull", { model }),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["local-models"] }),
  });
}

export function useStartOllama() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: () => api.post("/api/llm/local-models/start"),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["local-models"] }),
  });
}

export function useCancelJob() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (job: { file: string; started?: string }) =>
      api.post("/api/process/cancel", job),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["status"] }),
  });
}

export function useSetKey() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (v: { provider: string; key: string }) => api.post("/api/llm/key", v),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["llm"] }),
  });
}

export function useSetModel() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (v: { provider: string; model: string }) =>
      api.post("/api/llm/model", v),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["llm"] });
      qc.invalidateQueries({ queryKey: ["health"] });
    },
  });
}

export function useSetSteps() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (steps: Steps) => api.post("/api/config/steps", steps),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["config"] }),
  });
}

export function useSetWatchDir() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (watch_dir: string) => api.post("/api/config/watch-dir", { watch_dir }),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["config"] }),
  });
}

export function useProcessFile() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (v: { file: string; mode?: string }) =>
      api.post("/api/process", { file: v.file, mode: v.mode ?? "full" }),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["meetings"] }),
  });
}

export function useUploadFile() {
  const qc = useQueryClient();
  const [progress, setProgress] = useState<number | null>(null);
  const mutation = useMutation({
    mutationFn: (v: { file: File; mode?: string }) =>
      uploadFile(
        `/api/process/upload?mode=${encodeURIComponent(v.mode ?? "full")}`,
        v.file,
        setProgress,
      ),
    onMutate: () => setProgress(0),
    onSettled: () => setProgress(null),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["meetings"] }),
  });
  return { ...mutation, progress };
}

export function useDeleteMeeting() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (id: string) => api.del(`/api/meetings/${encodeURIComponent(id)}`),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["meetings"] }),
  });
}

export function useSummarizeMeeting() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (id: string) =>
      api.post(`/api/meetings/${encodeURIComponent(id)}/summarize`),
    onSuccess: (_d, id) => {
      qc.invalidateQueries({ queryKey: ["status"] });
      qc.invalidateQueries({ queryKey: ["meetings"] });
      qc.invalidateQueries({ queryKey: ["history"] });
      qc.invalidateQueries({ queryKey: ["meeting-log", id] });
    },
  });
}

export function useTranscribeMeeting() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (id: string) =>
      api.post(`/api/meetings/${encodeURIComponent(id)}/transcribe`),
    onSuccess: (_d, id) => {
      qc.invalidateQueries({ queryKey: ["status"] });
      qc.invalidateQueries({ queryKey: ["meetings"] });
      qc.invalidateQueries({ queryKey: ["history"] });
      qc.invalidateQueries({ queryKey: ["meeting-log", id] });
    },
  });
}

export const useGenerationLog = (id: string) =>
  useQuery({
    queryKey: ["meeting-log", id],
    queryFn: () => api.get<GenerationLogEntry[]>(`/api/meetings/${encodeURIComponent(id)}/log`),
    enabled: !!id,
    refetchInterval: 4000,
  });

export const useMeetingSource = (id: string) =>
  useQuery({
    queryKey: ["meeting-source", id],
    queryFn: () => api.get<SourceInfo>(`/api/meetings/${encodeURIComponent(id)}/source`),
    enabled: !!id,
  });

export function useDeleteMeetingSource() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (id: string) =>
      api.del(`/api/meetings/${encodeURIComponent(id)}/source`),
    onSuccess: (_d, id) => {
      qc.invalidateQueries({ queryKey: ["meeting-source", id] });
      qc.invalidateQueries({ queryKey: ["meeting-log", id] });
    },
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
