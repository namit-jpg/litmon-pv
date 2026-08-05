import { useEffect, useState } from "react";
import { Link, Navigate, Route, Routes, useNavigate } from "react-router-dom";
import { useAuth } from "./auth";
import { api, Presence } from "./api";
import LoginPage from "./pages/LoginPage";
import QueuePage from "./pages/QueuePage";
import ArticlePage from "./pages/ArticlePage";
import AdminPage from "./pages/AdminPage";
import ArchivePage from "./pages/ArchivePage";
import AuditPage from "./pages/AuditPage";
import OpsPage from "./pages/OpsPage";
import SearchRunPage from "./pages/SearchRunPage";
import DashboardPage from "./pages/DashboardPage";
import ProductSearchPage from "./pages/ProductSearchPage";
import AlertsBar from "./components/AlertsBar";

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

function Shell({ children }: { children: React.ReactNode }) {
  const { user, logout } = useAuth();
  const nav = useNavigate();
  return (
    <div className="app">
      <header className="topbar">
        <div className="brand">
          <Link to="/">LitMon-PV</Link>
          <span className="badge">Pilot — not GxP validated</span>
        </div>
        <nav>
          <Link to="/dashboard">Dashboard</Link>
          <Link to="/?tab=all">My Work</Link>
          <Link to="/product-search">Product Search</Link>
          <Link to="/archive">Archive</Link>
          {canSeeOps(user?.role) && (
            <>
              <Link to="/ops">Ops</Link>
              <Link to="/audit">Audit</Link>
              <Link to="/admin">Admin</Link>
            </>
          )}
        </nav>
        <AlertsBar />
        <PresenceControl />
        <div className="userbox">
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
      <main className="main">{children}</main>
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
      <Route
        path="/"
        element={
          <Private>
            <QueuePage />
          </Private>
        }
      />
      <Route
        path="/dashboard"
        element={
          <Private>
            <DashboardPage />
          </Private>
        }
      />
      <Route
        path="/articles/:id"
        element={
          <Private>
            <ArticlePage />
          </Private>
        }
      />
      <Route
        path="/archive"
        element={
          <Private>
            <ArchivePage />
          </Private>
        }
      />
      <Route
        path="/product-search"
        element={
          <Private>
            <ProductSearchPage />
          </Private>
        }
      />
      <Route
        path="/audit"
        element={
          <OpsOnly>
            <AuditPage />
          </OpsOnly>
        }
      />
      <Route
        path="/ops"
        element={
          <OpsOnly>
            <OpsPage />
          </OpsOnly>
        }
      />
      <Route
        path="/admin"
        element={
          <OpsOnly>
            <AdminPage />
          </OpsOnly>
        }
      />
      <Route
        path="/search-runs/:id"
        element={
          <Private>
            <SearchRunPage />
          </Private>
        }
      />
    </Routes>
  );
}
