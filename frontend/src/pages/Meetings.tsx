import { useState } from "react";
import { Link } from "react-router-dom";
import { Trash2, Search } from "lucide-react";
import { Card } from "../components/Card";
import { EmptyState } from "../components/EmptyState";
import { ConfirmDialog } from "../components/ConfirmDialog";
import { useToast } from "../components/Toast";
import { useMeetings, useDeleteMeeting } from "../hooks/useApi";
import { ApiError } from "../api/client";

export function Meetings() {
  const meetings = useMeetings();
  const del = useDeleteMeeting();
  const toast = useToast();
  const [q, setQ] = useState("");
  const [pending, setPending] = useState<string | null>(null);

  const items = (meetings.data ?? []).filter((m) => m.title.toLowerCase().includes(q.toLowerCase()));

  const confirmDelete = () => {
    if (!pending) return;
    del.mutate(pending, {
      onSuccess: () => toast("ok", "Reunião apagada."),
      onError: (e) => toast("err", e instanceof ApiError ? e.message : "Erro"),
    });
    setPending(null);
  };

  return (
    <Card title="Reuniões" actions={
      <div className="flex items-center gap-1.5 rounded-lg border border-slate-300 px-2">
        <Search size={15} className="text-slate-400" />
        <input value={q} onChange={(e) => setQ(e.target.value)} placeholder="Buscar…"
          className="py-1.5 text-sm outline-none" />
      </div>
    }>
      {items.length > 0 ? (
        <table className="w-full text-sm">
          <thead className="text-left text-xs uppercase text-slate-400">
            <tr><th className="py-2">Título</th><th>Data</th><th>Duração</th><th>Tarefas</th><th></th></tr>
          </thead>
          <tbody className="divide-y divide-slate-100">
            {items.map((m) => (
              <tr key={m.id} className="hover:bg-slate-50">
                <td className="py-2">
                  <div className="flex items-center gap-2">
                    <Link to={`/meetings/${encodeURIComponent(m.id)}`} className="font-medium hover:text-brand">{m.title}</Link>
                    {m.meeting_type && (
                      <span className="rounded-full bg-brand/10 px-2 py-0.5 text-xs font-medium text-brand">{m.meeting_type}</span>
                    )}
                  </div>
                  {m.purpose && <p className="text-xs text-slate-400">{m.purpose}</p>}
                </td>
                <td className="text-slate-500">{m.created || "—"}</td>
                <td className="text-slate-500">{m.duration || "—"}</td>
                <td className="text-slate-500">{m.task_count}</td>
                <td className="text-right">
                  <button onClick={() => setPending(m.id)} className="text-slate-400 hover:text-rose-600"><Trash2 size={16} /></button>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      ) : (
        <EmptyState title="Nenhuma reunião encontrada" />
      )}
      <ConfirmDialog open={!!pending} title="Apagar esta reunião?" onConfirm={confirmDelete} onCancel={() => setPending(null)} />
    </Card>
  );
}
