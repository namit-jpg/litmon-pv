import { Link, Navigate, Route, Routes, useNavigate } from "react-router-dom";
import { useAuth } from "./auth";
import LoginPage from "./pages/LoginPage";
import QueuePage from "./pages/QueuePage";
import ArticlePage from "./pages/ArticlePage";
import AdminPage from "./pages/AdminPage";
import ArchivePage from "./pages/ArchivePage";
import AuditPage from "./pages/AuditPage";
import OpsPage from "./pages/OpsPage";
import SearchRunPage from "./pages/SearchRunPage";
import DashboardPage from "./pages/DashboardPage";
import AlertsBar from "./components/AlertsBar";

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
          <Link to="/archive">Archive</Link>
          <Link to="/ops">Ops</Link>
          <Link to="/audit">Audit</Link>
          <Link to="/admin">Admin</Link>
        </nav>
        <AlertsBar />
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
        path="/audit"
        element={
          <Private>
            <AuditPage />
          </Private>
        }
      />
      <Route
        path="/ops"
        element={
          <Private>
            <OpsPage />
          </Private>
        }
      />
      <Route
        path="/admin"
        element={
          <Private>
            <AdminPage />
          </Private>
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
