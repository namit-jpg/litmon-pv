import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { api, ArticleFilters, DashboardMetrics, DashboardSummary } from "../api";
import { useAuth } from "../auth";
import DashboardCharts from "../components/DashboardCharts";

export default function DashboardPage() {
  const { user } = useAuth();
  // Reviewers carry a personal queue, so "My dashboard" is the useful default.
  // Admins and PV leads do not, and would otherwise land on an empty view.
  const carriesOwnQueue =
    user?.role === "reviewer" || user?.role === "senior_reviewer";
  const [mineOnly, setMineOnly] = useState(carriesOwnQueue);
  const [summary, setSummary] = useState<DashboardSummary | null>(null);
  const [metrics, setMetrics] = useState<DashboardMetrics | null>(null);
  const [error, setError] = useState("");

  async function load() {
    setError("");
    try {
      const [legacySummary, phase3Metrics] = await Promise.all([
        api.dashboard(mineOnly),
        api.dashboardMetrics(mineOnly),
      ]);
      setSummary(legacySummary);
      setMetrics(phase3Metrics);
    } catch (e) {
      setError(String(e));
    }
  }

  useEffect(() => {
    load();
  }, [mineOnly]);

  const workspaceLink = (filter: ArticleFilters) => {
    const query = new URLSearchParams();
    if (mineOnly) query.set("view", "mine");
    Object.entries(filter).forEach(([key, value]) => {
      if (value != null && value !== false) query.set(key, String(value));
    });
    return `/?${query.toString()}`;
  };

  return (
    <div>
      <div className="page-head">
        <div>
          <h1>PV Dashboard</h1>
          <p className="muted">Assignment, signal, review, and workload overview.</p>
        </div>
        <div className="tabs">
          <button className={mineOnly ? "tab active" : "tab"} onClick={() => setMineOnly(true)}>
            My dashboard
          </button>
          <button className={!mineOnly ? "tab active" : "tab"} onClick={() => setMineOnly(false)}>
            All work
          </button>
        </div>
      </div>
      {error && <div className="error">{error}</div>}
      {!summary || !metrics ? (
        <p className="muted">Loading dashboard…</p>
      ) : (
        <>
          <div className="dashboard-grid metric-grid">
            {metrics.metrics.map((metric) => (
              <Link className="dashboard-card" to={workspaceLink(metric.filter)} key={metric.key}>
                <span>{metric.label}</span>
                <strong>{metric.count}</strong>
                <small>Open work list →</small>
              </Link>
            ))}
          </div>
          <section className="card">
            <h2>Alerts by priority</h2>
            <div className="dashboard-grid">
              {metrics.alerts_by_priority.map((metric) => (
                <Link className="dashboard-card" key={metric.key} to={`/alerts?unread=false&priority=${metric.key.replace("alerts_", "")}`}>
                  <span>{metric.label}</span><strong>{metric.count}</strong><small>Open alert inbox →</small>
                </Link>
              ))}
              {metrics.alerts_by_priority.length === 0 ? <p className="muted">No alerts recorded.</p> : null}
            </div>
          </section>
          <section className="card">
            <h2>Monitoring coverage</h2>
            <div className="dashboard-grid">
              {metrics.results_by_product.map((row) => <Link className="dashboard-card" key={`product-${row.product_id}`} to={workspaceLink(row.filter)}><span>{row.product_name}</span><strong>{row.count}</strong><small>Results by product →</small></Link>)}
              {metrics.results_by_ingredient.map((row) => <Link className="dashboard-card" key={`ingredient-${row.active_ingredient_id}`} to={workspaceLink(row.filter)}><span>{row.active_ingredient_name}</span><strong>{row.count}</strong><small>Results by ingredient / API →</small></Link>)}
              {metrics.results_by_source.map((row) => <Link className="dashboard-card" key={`source-${row.literature_source_id}`} to={workspaceLink(row.filter)}><span>{row.literature_source_name}</span><strong>{row.count}</strong><small>Results by source →</small></Link>)}
            </div>
          </section>
          <section className="card">
            <h2>Search completion status</h2>
            {metrics.search_completion_status.length === 0 ? <p className="muted">No product searches have run yet.</p> : (
              <table className="table"><thead><tr><th>Product</th><th>Last status</th><th /></tr></thead><tbody>{metrics.search_completion_status.map((row) => <tr key={row.product_id}><td>{row.product_name}</td><td><span className="pill">{row.status}</span></td><td><Link className="btn ghost" to={workspaceLink(row.filter)}>Open results</Link></td></tr>)}</tbody></table>
            )}
          </section>
          <DashboardCharts summary={summary} />
        </>
      )}
    </div>
  );
}
