export function ConfirmDialog({ open, title, onConfirm, onCancel }: {
  open: boolean; title: string; onConfirm: () => void; onCancel: () => void;
}) {
  if (!open) return null;
  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40" onClick={onCancel}>
      <div className="w-80 rounded-xl bg-white p-5 shadow-xl" onClick={(e) => e.stopPropagation()}>
        <p className="mb-4 font-medium text-slate-800">{title}</p>
        <div className="flex justify-end gap-2">
          <button className="rounded-lg px-3 py-1.5 text-sm text-slate-600 hover:bg-slate-100" onClick={onCancel}>Cancelar</button>
          <button className="rounded-lg bg-rose-600 px-3 py-1.5 text-sm text-white hover:bg-rose-700" onClick={onConfirm}>Confirmar</button>
        </div>
      </div>
    </div>
  );
}
