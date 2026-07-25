import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { api } from "../api";

export default function OpsPage() {
  const [metrics, setMetrics] = useState<Record<string, unknown> | null>(null);
  const [overdue, setOverdue] = useState<Record<string, unknown> | null>(null);
  const [jobs, setJobs] = useState<Record<string, unknown>[]>([]);
  const [error, setError] = useState("");
  const [msg, setMsg] = useState("");
  const [busy, setBusy] = useState(false);

  async function load() {
    setError("");
    try {
      const [m, o, j] = await Promise.all([
        api.opsMetrics().catch(() => api.publicMetrics()),
        api.slaOverdue(),
        api.jobs(),
      ]);
      setMetrics(m);
      setOverdue(o);
      setJobs(j);
    } catch (e) {
      setError(String(e));
    }
  }

  useEffect(() => {
    load();
    const t = setInterval(load, 15000);
    return () => clearInterval(t);
  }, []);

  async function notifySla() {
    setBusy(true);
    setMsg("");
    try {
      const r = await api.slaNotify();
      setMsg(`SLA check job #${r.job_id} enqueued`);
      await load();
    } catch (e) {
      setError(String(e));
    } finally {
      setBusy(false);
    }
  }

  async function batchRescoreOpen() {
    setBusy(true);
    setMsg("");
    try {
      const r = await api.batchRescore({ all_open: true });
      setMsg(`Batch rescore job #${r.id} enqueued`);
      await load();
    } catch (e) {
      setError(String(e));
    } finally {
      setBusy(false);
    }
  }

  async function retry(id: number) {
    try {
      const j = await api.retryJob(id);
      setMsg(`Retried as job #${j.id}`);
      await load();
    } catch (e) {
      setError(String(e));
    }
  }

  const sla = (metrics?.sla || {}) as Record<string, unknown>;
  const scoring = (metrics?.scoring || {}) as Record<string, unknown>;
  const search = (metrics?.search || {}) as Record<string, unknown>;
  const requests = (metrics?.requests || {}) as Record<string, unknown>;
  const jobStats = (metrics?.jobs || {}) as Record<string, unknown>;

  return (
    <div>
      <div className="page-head">
        <div>
          <h1>Operations</h1>
          <p className="muted">
            Metrics, SLA breaches, background jobs — pilot hardening dashboard
          </p>
        </div>
        <button className="btn" onClick={load}>
          Refresh
        </button>
      </div>

      {msg && <div className="ok-banner">{msg}</div>}
      {error && <div className="error">{error}</div>}

      <div className="stat-row">
        <div className="stat danger">
          <span>SLA overdue</span>
          <strong>{String(overdue?.count ?? sla.overdue_total ?? 0)}</strong>
        </div>
        <div className="stat">
          <span>Score avg ms</span>
          <strong>{String(scoring.avg_latency_ms ?? "—")}</strong>
        </div>
        <div className="stat">
          <span>Search runs</span>
          <strong>{String(search.runs ?? 0)}</strong>
        </div>
        <div className="stat">
          <span>Search failures</span>
          <strong>{String(search.failures ?? 0)}</strong>
        </div>
        <div className="stat">
          <span>HTTP errors</span>
          <strong>{String(requests.errors ?? 0)}</strong>
        </div>
        <div className="stat">
          <span>Jobs failed</span>
          <strong>{String(jobStats.failed ?? 0)}</strong>
        </div>
      </div>

      <section className="card">
        <h2>Actions</h2>
        <div className="row-actions wrap">
          <button className="btn primary" disabled={busy} onClick={notifySla}>
            Run SLA check / notify
          </button>
          <button className="btn" disabled={busy} onClick={batchRescoreOpen}>
            Batch rescore all open
          </button>
        </div>
      </section>

      <section className="card">
        <h2>Overdue articles</h2>
        {!overdue || Number(overdue.count) === 0 ? (
          <p className="muted">None overdue — good.</p>
        ) : (
          <table className="table">
            <thead>
              <tr>
                <th>Hours over</th>
                <th>Queue</th>
                <th>PMID</th>
                <th>Title</th>
              </tr>
            </thead>
            <tbody>
              {(overdue.items as Record<string, unknown>[]).map((i) => (
                <tr key={String(i.id)}>
                  <td className="sla-red">{String(i.hours_overdue)}</td>
                  <td>{String(i.queue)}</td>
                  <td>{String(i.pmid)}</td>
                  <td>
                    <Link to={`/articles/${i.id}`}>{String(i.title)}</Link>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </section>

      <section className="card">
        <h2>Background jobs</h2>
        {jobs.length === 0 ? (
          <p className="muted">No jobs yet</p>
        ) : (
          <table className="table">
            <thead>
              <tr>
                <th>ID</th>
                <th>Type</th>
                <th>Status</th>
                <th>Attempts</th>
                <th>Error</th>
                <th></th>
              </tr>
            </thead>
            <tbody>
              {jobs.map((j) => (
                <tr key={String(j.id)}>
                  <td>{String(j.id)}</td>
                  <td>{String(j.job_type)}</td>
                  <td>
                    <span
                      className={
                        j.status === "failed"
                          ? "pill danger"
                          : j.status === "completed"
                            ? "pill"
                            : "pill queue-priority"
                      }
                    >
                      {String(j.status)}
                    </span>
                  </td>
                  <td>{String(j.attempts)}</td>
                  <td className="clip" title={String(j.error_message || "")}>
                    {String(j.error_message || "—").slice(0, 80)}
                  </td>
                  <td>
                    {j.status === "failed" && (
                      <button className="btn" onClick={() => retry(Number(j.id))}>
                        Retry
                      </button>
                    )}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </section>

      {metrics && (
        <section className="card">
          <h2>Raw metrics snapshot</h2>
          <pre className="code-block" style={{ maxHeight: 320, overflow: "auto" }}>
            {JSON.stringify(metrics, null, 2)}
          </pre>
        </section>
      )}
    </div>
  );
}
