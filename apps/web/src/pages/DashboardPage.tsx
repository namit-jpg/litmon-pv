import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { api, ArticleFilters, DashboardMetrics, DashboardSummary } from "../api";
import { useAuth } from "../auth";
import DashboardCharts from "../components/DashboardCharts";

function formatRunAt(value: string | null) {
  return value ? new Date(value).toLocaleString() : "—";
}

/** Severity band a tile is painted in. Empty string leaves the tile neutral. */
type Tone = "crit" | "warn" | "ok" | "";

/**
 * A count carries no colour on its own — the measure decides which direction is
 * bad. Twelve articles screened is neither good nor bad news; twelve reviews
 * past their SLA is a breach. So the tone comes from the metric key, and the
 * count only decides whether that meaning is currently in play.
 *
 * Three bands, and no numeric thresholds anywhere: `crit` is a commitment
 * already missed, `warn` is work still owed, `ok` is a queue standing empty.
 * Volume measures stay neutral rather than being forced into a band, because a
 * threshold picked here would be invented rather than agreed with the partner.
 */
function metricTone(key: string, count: number): Tone {
  switch (key) {
    // Past an SLA is a breach, not a backlog: one is already too many.
    case "overdue_reviews":
      return count > 0 ? "crit" : "ok";
    // An unresolved potential signal is the case this whole pipeline exists to
    // surface, so it outranks anything queued behind it.
    case "potential_signals":
      return count > 0 ? "crit" : "ok";
    // Records the pipeline could not finish. Recoverable, but invisible to
    // review until someone clears them — a silent gap in coverage.
    case "invalid_or_failed":
      return count > 0 ? "warn" : "ok";
    // Queued work. Whether the queue is long is what `overdue_reviews` answers;
    // here only empty versus not-empty is a fact rather than a judgement.
    case "awaiting_review":
      return count > 0 ? "warn" : "ok";
    // Approved but not yet filed is work still owed to a regulator.
    case "approved_for_submission":
      return count > 0 ? "warn" : "ok";
    // Finished work, and the only measure where a larger number is plainly
    // better.
    case "submitted":
      return count > 0 ? "ok" : "";
    // Volumes: identified, screened, relevant, irrelevant, retained. Neither
    // direction is good or bad, so they stay uncoloured and the coloured tiles
    // keep their meaning.
    default:
      return "";
  }
}

/**
 * Search completion, coloured by what the run actually did. The values come
 * from two places — `SearchRunStatus` for a run, and the schedule's own
 * `last_status` — so both vocabularies are handled here. A run in flight stays
 * neutral: it has not succeeded or failed yet, and colouring it would age
 * badly on a dashboard that refreshes.
 */
function searchStatusTone(status: string): Tone {
  switch (status) {
    case "failed":
      return "crit";
    // Not a crash, but coverage has a hole in it either way: the product is
    // configured for monitoring and no search is currently reaching it.
    case "not_run":
    case "expired":
    case "no_active_search_string":
      return "warn";
    case "completed":
      return "ok";
    // pending, running — still in flight.
    default:
      return "";
  }
}

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
          {/* Without this the colours are decoration. It says what each band
              means once, so a tile does not have to be hovered to be read. */}
          <div className="tone-legend no-print">
            <span className="tone-key crit">Past a commitment</span>
            <span className="tone-key warn">Work still owed</span>
            <span className="tone-key ok">Clear</span>
            <span className="tone-key">Volume — no direction</span>
          </div>
          <div className="dashboard-grid metric-grid">
            {metrics.metrics.map((metric) => (
              <Link
                className={`dashboard-card ${metricTone(metric.key, metric.count)}`.trim()}
                to={workspaceLink(metric.filter)}
                key={metric.key}
              >
                <span>{metric.label}</span>
                <strong>{metric.count}</strong>
                <small>Open work list →</small>
              </Link>
            ))}
          </div>
          <section className="card">
            <h2>Alerts by priority</h2>
            <div className="dashboard-grid">
              {metrics.alerts_by_priority.map((metric) => {
                const priority = metric.key.replace("alerts_", "");
                return (
                  <Link
                    className={`dashboard-card ${priority === "high" && metric.count > 0 ? "crit" : ""}`.trim()}
                    key={metric.key}
                    to={`/alerts?unread=false&priority=${priority}`}
                  >
                    <span>{metric.label}</span><strong>{metric.count}</strong><small>Open alert inbox →</small>
                  </Link>
                );
              })}
              {metrics.alerts_by_priority.length === 0 ? <p className="muted">No alerts recorded.</p> : null}
            </div>
          </section>
          <section className="card">
            <h2>Monitoring coverage</h2>
            {/* Deliberately uncoloured: these are volumes per product, ingredient
                and source. A big number here means a productive search, not a
                problem, so painting them would drain the colour of meaning. */}
            <div className="dashboard-grid">
              {metrics.results_by_product.map((row) => <Link className="dashboard-card" key={`product-${row.product_id}`} to={workspaceLink(row.filter)}><span>{row.product_name}</span><strong>{row.count}</strong><small>Results by product →</small></Link>)}
              {metrics.results_by_ingredient.map((row) => <Link className="dashboard-card" key={`ingredient-${row.active_ingredient_id}`} to={workspaceLink(row.filter)}><span>{row.active_ingredient_name}</span><strong>{row.count}</strong><small>Results by ingredient / API →</small></Link>)}
              {metrics.results_by_source.map((row) => <Link className="dashboard-card" key={`source-${row.literature_source_id}`} to={workspaceLink(row.filter)}><span>{row.literature_source_name}</span><strong>{row.count}</strong><small>Results by source →</small></Link>)}
            </div>
          </section>
          <section className="card">
            <h2>Search completion status</h2>
            {metrics.search_completion_status.length === 0 ? <p className="muted">No active monitored products are configured.</p> : (
              <table className="table"><thead><tr><th>Product</th><th>Last status</th><th>Run</th><th>Last run</th><th /></tr></thead><tbody>{metrics.search_completion_status.map((row) => <tr key={row.product_id}><td>{row.product_name}</td><td><span className={`pill ${searchStatusTone(row.status)}`.trim()}>{row.status.replace(/_/g, " ")}</span></td><td>{row.origin || "—"}</td><td>{formatRunAt(row.last_run_at)}</td><td><Link className="btn ghost" to={workspaceLink(row.filter)}>Open results</Link></td></tr>)}</tbody></table>
            )}
          </section>
          <DashboardCharts summary={summary} />
        </>
      )}
    </div>
  );
}
