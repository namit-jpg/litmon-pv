import { useCallback, useEffect, useState } from "react";
import { Link, Navigate, NavLink, Route, Routes, useNavigate } from "react-router-dom";
import { useAuth } from "./auth";
import { api, Presence } from "./api";
import {
  resolvedTheme,
  saveTheme,
  storedTheme,
  type ThemeChoice,
} from "./theme";
import LoginPage from "./pages/LoginPage";
import WorkspacePage from "./pages/WorkspacePage";
import DetectionReportPage from "./pages/DetectionReportPage";
import AdminPage from "./pages/AdminPage";
import ArchivePage from "./pages/ArchivePage";
import AuditPage from "./pages/AuditPage";
import OpsPage from "./pages/OpsPage";
import SearchRunPage from "./pages/SearchRunPage";
import DashboardPage from "./pages/DashboardPage";
import AlertsPage from "./pages/AlertsPage";
import ChatPage from "./pages/ChatPage";
import SubmissionPage from "./pages/SubmissionPage";
import ProductsPage from "./pages/ProductsPage";
import SourcesPage from "./pages/SourcesPage";
import SchedulePage from "./pages/SchedulePage";
import ProductSearchPage from "./pages/ProductSearchPage";

/** Operations surfaces. Reviewers work the queue; they do not run the system. */
const OPS_ROLES = ["pv_lead", "admin"];

function canSeeOps(role?: string): boolean {
  return OPS_ROLES.includes(role || "");
}

function PresenceControl() {
  const [presence, setPresence] = useState<Presence | null>(null);
  useEffect(() => {
    let active = true;
    const load = () =>
      api.presence().then((p) => active && setPresence(p)).catch(() => undefined);
    load();
    const timer = window.setInterval(load, 15000);
    return () => {
      active = false;
      window.clearInterval(timer);
    };
  }, []);
  if (!presence) return null;
  return (
    <div className="presence-control" title="Omni-style routing presence and capacity">
      <span className={`presence-dot ${presence.status}`} />
      <select
        aria-label="Reviewer presence"
        value={presence.status}
        onChange={async (event) => {
          const next = event.target.value as Presence["status"];
          try {
            setPresence(await api.updatePresence(next));
          } catch {
            // Keep the last known state during a transient pilot API failure.
          }
        }}
      >
        <option value="available">Available</option>
        <option value="busy">Busy</option>
        <option value="offline">Offline</option>
      </select>
      <span className="presence-capacity">
        {presence.active_work_count}/{presence.capacity_limit}
      </span>
    </div>
  );
}

/** Light / dark / system switch. Sits in the topbar beside the user. */
function ThemePicker() {
  const [choice, setChoice] = useState<ThemeChoice>(() => storedTheme());

  // Re-render on an OS theme change so the label stays truthful while the
  // choice is "system".
  useEffect(() => {
    const mq = window.matchMedia("(prefers-color-scheme: dark)");
    const onChange = () => setChoice((current) => current);
    mq.addEventListener("change", onChange);
    return () => mq.removeEventListener("change", onChange);
  }, []);

  const resolved = resolvedTheme(choice);

  return (
    <div
      className="theme-picker"
      title={
        choice === "system"
          ? `Following your system setting (${resolved})`
          : `Theme: ${choice}`
      }
    >
      <span className="theme-glyph" aria-hidden="true">
        {resolved === "dark" ? "☾" : "☀"}
      </span>
      <select
        aria-label="Colour theme"
        value={choice}
        onChange={(event) => {
          const next = event.target.value as ThemeChoice;
          setChoice(next);
          saveTheme(next);
        }}
      >
        <option value="system">System</option>
        <option value="light">Light</option>
        <option value="dark">Dark</option>
      </select>
    </div>
  );
}

type RailCounts = { work: number; alerts: number };

/** Left rail. Groups follow the wireframe: Monitor, Regulatory, Configure. */
function Rail({ role }: { role?: string }) {
  const [counts, setCounts] = useState<RailCounts>({ work: 0, alerts: 0 });

  const load = useCallback(async () => {
    try {
      const [folders, alerts] = await Promise.all([
        api.workspaceFolders({ mine_only: true }),
        api.alerts({ unread_only: true }),
      ]);
      // "Work" is everything still needing this reviewer, which is the open
      // folders rather than the whole queue — a count including Archived
      // would never go down and would stop meaning anything.
      const open = new Set([
        "new_alerts",
        "awaiting_review",
        "under_assessment",
        "exceptions",
      ]);
      setCounts({
        work: folders.folders
          .filter((f) => open.has(f.key))
          .reduce((total, f) => total + f.count, 0),
        alerts: alerts.length,
      });
    } catch {
      // A failed count must not blank the navigation.
    }
  }, []);

  useEffect(() => {
    load();
    const timer = window.setInterval(load, 30000);
    return () => window.clearInterval(timer);
  }, [load]);

  const link = (to: string, label: string, count?: number, crit?: boolean) => (
    <NavLink
      to={to}
      end={to === "/"}
      className={({ isActive }) => `rail-link${isActive ? " is-active" : ""}`}
    >
      {label}
      {count ? <span className={`ct${crit ? " crit" : ""}`}>{count}</span> : null}
    </NavLink>
  );

  return (
    <nav className="rail" aria-label="Main">
      <div className="rail-tenant">
        <span className="lbl">Client</span>
        <div className="val">
          <span>LitMon-PV pilot</span>
          <i>{role?.replace("_", " ")}</i>
        </div>
      </div>

      <div className="rail-group">Monitor</div>
      {link("/dashboard", "Dashboard")}
      {link("/", "My workspace", counts.work, counts.work > 0)}
      {link("/alerts", "Alerts", counts.alerts, counts.alerts > 0)}
      {link("/chat", "Chat")}
      {link("/archive", "Archive")}

      <div className="rail-group">Regulatory</div>
      {link("/submission", "Submission & storage")}
      {canSeeOps(role) ? link("/audit", "Audit trail") : null}

      <div className="rail-group">Configure</div>
      {link("/product-search", "Product search")}
      {canSeeOps(role) ? link("/products", "Products") : null}
      {canSeeOps(role) ? link("/sources", "Literature sources") : null}
      {canSeeOps(role) ? link("/schedule", "Search & schedule") : null}
      {canSeeOps(role) ? link("/ops", "Ops") : null}
      {canSeeOps(role) ? link("/admin", "Pilot tools") : null}
    </nav>
  );
}

function Shell({ children }: { children: React.ReactNode }) {
  const { user, logout } = useAuth();
  const nav = useNavigate();
  return (
    <div className="app">
      <header className="topbar">
        <div className="brand">
          <Link to="/dashboard">LitMon-PV</Link>
          <span className="badge">Pilot — not GxP validated</span>
        </div>
        <PresenceControl />
        <div className="userbox">
          <ThemePicker />
          <span>
            {user?.full_name} ({user?.role})
          </span>
          <button
            className="btn ghost"
            onClick={() => {
              logout();
              nav("/login");
            }}
          >
            Log out
          </button>
        </div>
      </header>
      <div className="shell">
        <Rail role={user?.role} />
        <main className="canvas">{children}</main>
      </div>
    </div>
  );
}

function Private({ children }: { children: React.ReactNode }) {
  const { token } = useAuth();
  if (!token) return <Navigate to="/login" replace />;
  return <Shell>{children}</Shell>;
}

/** Ops-only route. Hiding the nav link is not a guard — a reviewer can still
 *  type the URL — so the route itself redirects. The API enforces this too. */
function OpsOnly({ children }: { children: React.ReactNode }) {
  const { token, user } = useAuth();
  if (!token) return <Navigate to="/login" replace />;
  if (!canSeeOps(user?.role)) return <Navigate to="/dashboard" replace />;
  return <Shell>{children}</Shell>;
}

export default function App() {
  return (
    <Routes>
      <Route path="/login" element={<LoginPage />} />

      {/* Monitor */}
      <Route path="/" element={<Private><WorkspacePage /></Private>} />
      <Route path="/dashboard" element={<Private><DashboardPage /></Private>} />
      <Route path="/alerts" element={<Private><AlertsPage /></Private>} />
      <Route path="/chat" element={<Private><ChatPage /></Private>} />
      <Route path="/archive" element={<Private><ArchivePage /></Private>} />
      <Route path="/articles/:id" element={<Private><DetectionReportPage /></Private>} />

      {/* Regulatory */}
      <Route path="/submission" element={<Private><SubmissionPage /></Private>} />
      <Route path="/submission/:id" element={<Private><SubmissionPage /></Private>} />
      <Route path="/audit" element={<OpsOnly><AuditPage /></OpsOnly>} />

      {/* Configure */}
      <Route path="/product-search" element={<Private><ProductSearchPage /></Private>} />
      <Route path="/products" element={<OpsOnly><ProductsPage /></OpsOnly>} />
      <Route path="/sources" element={<OpsOnly><SourcesPage /></OpsOnly>} />
      <Route path="/schedule" element={<OpsOnly><SchedulePage /></OpsOnly>} />
      <Route path="/search-runs/:id" element={<Private><SearchRunPage /></Private>} />
      <Route path="/ops" element={<OpsOnly><OpsPage /></OpsOnly>} />
      <Route path="/admin" element={<OpsOnly><AdminPage /></OpsOnly>} />
    </Routes>
  );
}
