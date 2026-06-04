import { createContext, useCallback, useContext, useState, type ReactNode } from "react";

type Toast = { id: number; kind: "ok" | "err"; msg: string };
const ToastCtx = createContext<(kind: Toast["kind"], msg: string) => void>(() => {});

export function useToast() { return useContext(ToastCtx); }

export function ToastProvider({ children }: { children: ReactNode }) {
  const [items, setItems] = useState<Toast[]>([]);
  const push = useCallback((kind: Toast["kind"], msg: string) => {
    const id = Date.now() + Math.random();
    setItems((p) => [...p, { id, kind, msg }]);
    setTimeout(() => setItems((p) => p.filter((t) => t.id !== id)), 4000);
  }, []);
  return (
    <ToastCtx.Provider value={push}>
      {children}
      <div className="fixed bottom-4 right-4 z-50 flex flex-col gap-2">
        {items.map((t) => (
          <div key={t.id} className={`rounded-lg px-4 py-2 text-sm text-white shadow-lg ${
            t.kind === "ok" ? "bg-emerald-600" : "bg-rose-600"}`}>{t.msg}</div>
        ))}
      </div>
    </ToastCtx.Provider>
  );
}
