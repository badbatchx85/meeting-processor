import { useMemo, useState, useEffect } from "react";
import { DndContext, type DragEndEvent, PointerSensor, useSensor, useSensors } from "@dnd-kit/core";
import { useDroppable, useDraggable } from "@dnd-kit/core";
import { Download } from "lucide-react";
import { PageHeader } from "../components/PageHeader";
import { useTasks, useMoveTask } from "../hooks/useApi";
import { useToast } from "../components/Toast";
import type { Task } from "../api/types";
import { ApiError } from "../api/client";

const COLUMNS = ["A Fazer", "Em Progresso", "Concluído"];

function TaskCard({ task }: { task: Task }) {
  const { attributes, listeners, setNodeRef, transform } = useDraggable({ id: task.task_id, data: task });
  const style = transform ? { transform: `translate(${transform.x}px, ${transform.y}px)` } : undefined;
  return (
    <div ref={setNodeRef} style={style} {...listeners} {...attributes}
      className="cursor-grab rounded-lg border border-line bg-white p-3 text-sm shadow-sm active:cursor-grabbing">
      <p className="font-medium text-ink-soft">{task.description}</p>
      {task.assignee && <p className="mt-1 text-xs text-muted-soft">{task.assignee}</p>}
    </div>
  );
}

function Column({ name, tasks }: { name: string; tasks: Task[] }) {
  const { setNodeRef, isOver } = useDroppable({ id: name });
  return (
    <div ref={setNodeRef} className={`flex-1 rounded-card border p-3 transition-colors ${isOver ? "border-ink bg-line" : "border-line bg-line-soft/60"}`}>
      <h3 className="mb-3 flex items-center justify-between">
        <span className="eyebrow">{name}</span>
        <span className="rounded-full bg-surface px-2 py-0.5 font-mono text-[11px] tabular-nums text-muted-soft ring-1 ring-line">{tasks.length}</span>
      </h3>
      <div className="flex flex-col gap-2">
        {tasks.map((t) => <TaskCard key={t.task_id} task={t} />)}
      </div>
    </div>
  );
}

export function Tasks() {
  const query = useTasks();
  const move = useMoveTask();
  const toast = useToast();
  const sensors = useSensors(useSensor(PointerSensor, { activationConstraint: { distance: 5 } }));
  const [local, setLocal] = useState<Task[]>([]);
  useEffect(() => { if (query.data) setLocal(query.data); }, [query.data]);

  const byColumn = useMemo(() => {
    const map: Record<string, Task[]> = {};
    for (const c of COLUMNS) map[c] = [];
    for (const t of local) (map[t.column] ?? (map[t.column] = [])).push(t);
    return map;
  }, [local]);

  const onDragEnd = (e: DragEndEvent) => {
    const task = e.active.data.current as Task | undefined;
    const to = e.over?.id as string | undefined;
    if (!task || !to || to === task.column) return;
    setLocal((prev) => prev.map((t) => t.task_id === task.task_id ? { ...t, column: to } : t)); // optimistic
    move.mutate(
      { task_id: task.task_id, meeting_id: task.meeting_id, to_column: to },
      {
        onError: (err) => {
          setLocal((prev) => prev.map((t) => t.task_id === task.task_id ? { ...t, column: task.column } : t));
          toast("err", err instanceof ApiError ? err.message : "Falha ao mover");
        },
      },
    );
  };

  return (
    <div>
      <PageHeader
        index="03"
        eyebrow="Quadro"
        title="Tarefas"
        description="Arraste as tarefas entre as colunas. As mudanças são salvas na hora."
        actions={
          <div className="flex gap-1">
            {["csv", "json", "md", "txt"].map((ext) => (
              <a key={ext} href={`/api/tasks/export.${ext}`}
                className="flex items-center gap-1 rounded-md border border-line px-2 py-1 font-mono text-[11px] uppercase tracking-label text-muted transition-colors hover:border-ink hover:text-ink">
                <Download size={12} /> {ext.toUpperCase()}
              </a>
            ))}
          </div>
        }
      />
      <DndContext sensors={sensors} onDragEnd={onDragEnd}>
        <div className="flex gap-4">
          {COLUMNS.map((c) => <Column key={c} name={c} tasks={byColumn[c] ?? []} />)}
        </div>
      </DndContext>
    </div>
  );
}
