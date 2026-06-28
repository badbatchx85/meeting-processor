import { NavLink } from "react-router-dom";
import { LayoutDashboard, Video, KanbanSquare, Settings, Search } from "lucide-react";

const links = [
  { to: "/", label: "Dashboard", icon: LayoutDashboard, end: true },
  { to: "/meetings", label: "Reuniões", icon: Video, end: false },
  { to: "/search", label: "Busca", icon: Search, end: false },
  { to: "/tasks", label: "Tarefas", icon: KanbanSquare, end: false },
  { to: "/settings", label: "Configuração", icon: Settings, end: false },
];

export function Sidebar() {
  return (
    <aside className="flex w-60 shrink-0 flex-col border-r border-line bg-surface">
      {/* Wordmark */}
      <div className="flex items-center gap-3 px-5 py-6">
        <span className="grid h-9 w-9 place-items-center rounded-[9px] bg-ink">
          <svg viewBox="0 0 32 32" className="h-5 w-5" aria-hidden>
            <g stroke="#FAFAF9" strokeWidth="2.4" strokeLinecap="round">
              <path d="M9 12h14" /><path d="M9 17h14" /><path d="M9 22h8" />
            </g>
          </svg>
        </span>
        <div className="leading-none">
          <div className="font-display text-[17px] font-semibold tracking-tightest text-ink">
            Meeting&nbsp;Processor
          </div>
          <div className="eyebrow mt-1.5">Local · Offline</div>
        </div>
      </div>

      <nav className="flex flex-col gap-0.5 px-3 py-2">
        {links.map(({ to, label, icon: Icon, end }, i) => (
          <NavLink
            key={to}
            to={to}
            end={end}
            className={({ isActive }) =>
              `group relative flex items-center gap-3 rounded-lg px-3 py-2.5 text-sm transition-colors ${
                isActive ? "bg-line-soft text-ink" : "text-muted hover:bg-line-soft/60 hover:text-ink"
              }`
            }
          >
            {({ isActive }) => (
              <>
                <span
                  className={`absolute left-0 top-1/2 h-5 w-[3px] -translate-y-1/2 rounded-r bg-ink transition-opacity ${
                    isActive ? "opacity-100" : "opacity-0"
                  }`}
                />
                <span className="index-num w-4 text-center">{String(i + 1).padStart(2, "0")}</span>
                <Icon size={17} strokeWidth={2} className="shrink-0" />
                <span className="font-medium tracking-tight">{label}</span>
              </>
            )}
          </NavLink>
        ))}
      </nav>

      <div className="mt-auto px-5 py-5">
        <div className="border-t border-line pt-4">
          <p className="eyebrow">Processa</p>
          <p className="mt-2 text-[13px] leading-snug text-muted">
            Vídeo → transcrição → resumo → tarefas, na sua máquina.
          </p>
        </div>
      </div>
    </aside>
  );
}
