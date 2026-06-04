import { useMemo, useState, useEffect } from "react";
import { DndContext, type DragEndEvent, PointerSensor, useSensor, useSensors } from "@dnd-kit/core";
import { useDroppable, useDraggable } from "@dnd-kit/core";
import { Download } from "lucide-react";
import { Card } from "../components/Card";
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
      className="cursor-grab rounded-lg border border-slate-200 bg-white p-3 text-sm shadow-sm active:cursor-grabbing">
      <p className="font-medium text-slate-700">{task.description}</p>
      {task.assignee && <p className="mt-1 text-xs text-slate-400">{task.assignee}</p>}
    </div>
  );
}

function Column({ name, tasks }: { name: string; tasks: Task[] }) {
  const { setNodeRef, isOver } = useDroppable({ id: name });
  return (
    <div ref={setNodeRef} className={`flex-1 rounded-xl p-3 ${isOver ? "bg-brand/10" : "bg-slate-100"}`}>
      <h3 className="mb-3 flex items-center justify-between text-sm font-semibold text-slate-600">
        {name} <span className="rounded-full bg-white px-2 text-xs text-slate-400">{tasks.length}</span>
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
    <Card title="Tarefas (Kanban)" actions={
      <div className="flex gap-1 text-xs">
        {["csv", "json", "md", "txt"].map((ext) => (
          <a key={ext} href={`/api/tasks/export.${ext}`}
            className="flex items-center gap-1 rounded border border-slate-300 px-2 py-1 text-slate-600 hover:bg-slate-100">
            <Download size={12} /> {ext.toUpperCase()}
          </a>
        ))}
      </div>
    }>
      <DndContext sensors={sensors} onDragEnd={onDragEnd}>
        <div className="flex gap-4">
          {COLUMNS.map((c) => <Column key={c} name={c} tasks={byColumn[c] ?? []} />)}
        </div>
      </DndContext>
    </Card>
  );
}
