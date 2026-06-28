import { lazy } from "react";
import { Routes, Route } from "react-router-dom";
import { AppShell } from "./components/AppShell";

// Route-level code splitting: each page (and its heavy deps — react-markdown
// in MeetingDetail, @dnd-kit in Tasks) loads only when first visited.
const Dashboard = lazy(() =>
  import("./pages/Dashboard").then((m) => ({ default: m.Dashboard })),
);
const Meetings = lazy(() =>
  import("./pages/Meetings").then((m) => ({ default: m.Meetings })),
);
const MeetingDetail = lazy(() =>
  import("./pages/MeetingDetail").then((m) => ({ default: m.MeetingDetail })),
);
const Tasks = lazy(() =>
  import("./pages/Tasks").then((m) => ({ default: m.Tasks })),
);
const Settings = lazy(() =>
  import("./pages/Settings").then((m) => ({ default: m.Settings })),
);
const Search = lazy(() =>
  import("./pages/Search").then((m) => ({ default: m.Search })),
);

export default function App() {
  return (
    <Routes>
      <Route element={<AppShell />}>
        <Route index element={<Dashboard />} />
        <Route path="meetings" element={<Meetings />} />
        <Route path="meetings/:id" element={<MeetingDetail />} />
        <Route path="search" element={<Search />} />
        <Route path="tasks" element={<Tasks />} />
        <Route path="settings" element={<Settings />} />
      </Route>
    </Routes>
  );
}
