import { NavLink } from "react-router-dom";
import { LayoutDashboard, Video, KanbanSquare, Settings } from "lucide-react";

const links = [
  { to: "/", label: "Dashboard", icon: LayoutDashboard, end: true },
  { to: "/meetings", label: "Reuniões", icon: Video, end: false },
  { to: "/tasks", label: "Tarefas", icon: KanbanSquare, end: false },
  { to: "/settings", label: "Configuração", icon: Settings, end: false },
];

export function Sidebar() {
  return (
    <aside className="flex w-56 flex-col gap-1 border-r border-slate-200 bg-white p-3">
      <div className="mb-4 px-2 text-lg font-bold text-brand">Meeting Processor</div>
      {links.map(({ to, label, icon: Icon, end }) => (
        <NavLink key={to} to={to} end={end} className={({ isActive }) =>
          `flex items-center gap-2 rounded-lg px-3 py-2 text-sm font-medium ${
            isActive ? "bg-brand/10 text-brand" : "text-slate-600 hover:bg-slate-100"}`}>
          <Icon size={18} /> {label}
        </NavLink>
      ))}
    </aside>
  );
}
