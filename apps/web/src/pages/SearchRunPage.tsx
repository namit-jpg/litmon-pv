import { useEffect, useState } from "react";
import { Link, useNavigate, useParams } from "react-router-dom";
import { api, SearchRunDetail } from "../api";

function formatErr(e: unknown): string {
  const s = String(e);
  try {
    const j = JSON.parse(s);
    if (j?.detail?.message) return j.detail.message;
    if (typeof j?.detail === "string") return j.detail;
  } catch {
    /* plain text */
  }
  return s;
}

export default function SearchRunPage() {
  const { id } = useParams();
  const nav = useNavigate();
  const runId = Number(id);
  const [run, setRun] = useState<SearchRunDetail | null>(null);
  const [error, setError] = useState("");
  const [msg, setMsg] = useState("");
  const [busy, setBusy] = useState(false);

  async function load() {
    try {
      setError("");
      const r = await api.searchRun(runId);
      setRun(r);
    } catch (e) {
      setError(formatErr(e));
    }
  }

  useEffect(() => {
    if (!Number.isFinite(runId)) {
      setError("Invalid search run id");
      return;
    }
    load();
  }, [runId]);

  async function retry() {
    setBusy(true);
    setError("");
    setMsg("");
    try {
      const next = await api.retrySearchRun(runId);
      setMsg(`Retry started as search run #${next.id} (${next.status})`);
      if (next.status === "failed") {
        setError(String(next.error_message || "Retry failed"));
      }
      nav(`/search-runs/${next.id}`);
    } catch (e) {
      setError(formatErr(e));
    } finally {
      setBusy(false);
    }
  }

  if (!run && !error) {
    return <p className="muted">Loading search run…</p>;
  }

  return (
    <div>
      <div className="page-head">
        <div>
          <p className="muted">
            <Link to="/admin">← Admin</Link>
          </p>
          <h1>Search run #{runId}</h1>
          {run && (
            <p className="muted">
              {run.product_name ? `${run.product_name} · ` : ""}
              status=<strong>{run.status}</strong>
              {run.date_from && run.date_to
                ? ` · window ${run.date_from} → ${run.date_to}`
                : ""}
            </p>
          )}
        </div>
        {run && (run.status === "failed" || run.status === "completed") && (
          <button className="btn primary" disabled={busy} onClick={retry}>
            Retry search
          </button>
        )}
      </div>

      {msg && <div className="ok-banner">{msg}</div>}
      {error && <div className="error">{error}</div>}

      {run && (
        <>
          <section className="card">
            <h2>Run details</h2>
            <dl className="detail-grid">
              <div>
                <dt>Status</dt>
                <dd>
                  <span
                    className={
                      run.status === "failed"
                        ? "pill danger"
                        : run.status === "completed"
                          ? "pill ok"
                          : "pill"
                    }
                  >
                    {run.status}
                  </span>
                </dd>
              </div>
              <div>
                <dt>Hits / new / rehit</dt>
                <dd>
                  {run.hit_count} / {run.new_article_count} / {run.rehit_count}
                </dd>
              </div>
              <div>
                <dt>Triggered by</dt>
                <dd>{run.triggered_by || "—"}</dd>
              </div>
              <div>
                <dt>Started</dt>
                <dd>{run.started_at || "—"}</dd>
              </div>
              <div>
                <dt>Completed</dt>
                <dd>{run.completed_at || "—"}</dd>
              </div>
              <div>
                <dt>Search string id</dt>
                <dd>{run.search_string_id}</dd>
              </div>
            </dl>
            {run.error_message && (
              <div className="error" style={{ marginTop: "1rem" }}>
                <strong>Error:</strong> {run.error_message}
                <p className="hint" style={{ marginBottom: 0 }}>
                  Common fixes: set a real <code>NCBI_EMAIL</code>, add{" "}
                  <code>NCBI_API_KEY</code> for rate limits, then retry.
                </p>
              </div>
            )}
            <h3>Query snapshot</h3>
            <pre className="code-block">{run.query_snapshot}</pre>
          </section>

          <section className="card">
            <h2>
              Articles in this run ({run.articles.length})
            </h2>
            {run.articles.length === 0 ? (
              <p className="muted">
                No article appearances recorded
                {run.status === "failed" ? " (run failed before ingest)." : "."}
              </p>
            ) : (
              <table className="table">
                <thead>
                  <tr>
                    <th>PMID</th>
                    <th>Title</th>
                    <th>First seen</th>
                    <th>Score</th>
                    <th>Queue</th>
                    <th>Status</th>
                  </tr>
                </thead>
                <tbody>
                  {run.articles.map((a) => (
                    <tr key={a.id}>
                      <td>
                        <Link to={`/articles/${a.id}`}>{a.pmid}</Link>
                      </td>
                      <td className="clip">{a.title}</td>
                      <td>{a.is_first_seen ? "yes" : "rehit"}</td>
                      <td>
                        {a.composite != null ? a.composite.toFixed(2) : "—"}
                      </td>
                      <td>{a.queue || "—"}</td>
                      <td>{a.status}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            )}
          </section>
        </>
      )}
    </div>
  );
}
