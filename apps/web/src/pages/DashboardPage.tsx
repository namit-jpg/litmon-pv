import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { api, DashboardSummary } from "../api";
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
  const [error, setError] = useState("");

  async function load() {
    setError("");
    try {
      setSummary(await api.dashboard(mineOnly));
    } catch (e) {
      setError(String(e));
    }
  }

  useEffect(() => {
    load();
  }, [mineOnly]);

  const scope = mineOnly ? "view=mine" : "view=all";
  const cards = summary
    ? [
        ["Awaiting review", summary.awaiting_review, `/?${scope}&tab=all`],
        ["Unassigned triage", summary.unassigned, "/?view=all&tab=all"],
        ["Potential signals", summary.potential_signals, `/?${scope}&signal_status=potential_signal`],
        ["Confirmed signals", summary.confirmed_signals, `/?${scope}&signal_status=confirmed_signal`],
        ["Valid ICSR", summary.valid_icsr, `/?${scope}&status=disposition_valid_icsr`],
        ["Not relevant", summary.not_relevant, `/?${scope}&status=disposition_not_case`],
        ["Deferred", summary.deferred, `/?${scope}&status=deferred`],
        ["Overdue", summary.overdue, `/?${scope}&overdue=true`],
        ["Unread alerts", summary.unread_alerts, "/dashboard"],
      ] as const
    : [];

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
      {!summary ? (
        <p className="muted">Loading dashboard…</p>
      ) : (
        <>
          <div className="dashboard-grid">
            {cards.map(([label, value, href]) => (
              <Link className="dashboard-card" to={href} key={label}>
                <span>{label}</span>
                <strong>{value}</strong>
                <small>Open work list →</small>
              </Link>
            ))}
          </div>
          <DashboardCharts summary={summary} />
          <section className="card">
            <h2>Results by product</h2>
            {summary.by_product.length === 0 ? (
              <p className="muted">No literature results yet.</p>
            ) : (
              <div className="product-bars">
                {summary.by_product.map((product) => (
                  <Link
                    to={`/?${scope}&tab=all&product_id=${product.product_id}`}
                    className="product-bar"
                    key={product.product_id}
                  >
                    <span>{product.product_name}</span>
                    <strong>{product.count}</strong>
                  </Link>
                ))}
              </div>
            )}
          </section>
        </>
      )}
    </div>
  );
}
