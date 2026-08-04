import { useEffect, useState } from "react";
import { Link, useSearchParams } from "react-router-dom";
import { api, ArticleListItem, Product, QueueStats } from "../api";

const TABS: {
  key: string;
  label: string;
  queue?: string;
  status?: string;
}[] = [
  { key: "expedited", label: "Expedited", queue: "expedited" },
  { key: "priority", label: "Priority", queue: "priority" },
  { key: "standard", label: "Standard", queue: "standard" },
  { key: "qc_sample", label: "Auto-Clear QC", queue: "qc_sample" },
  { key: "second_review", label: "2nd review", status: "second_review" },
  { key: "deferred", label: "Deferred", status: "deferred" },
  { key: "all", label: "All open" },
];

function slaClass(due?: string) {
  if (!due) return "";
  const ms = new Date(due).getTime() - Date.now();
  const h = ms / 36e5;
  if (h < 0) return "sla-red";
  if (h < 24) return "sla-amber";
  return "sla-green";
}

function formatDue(due?: string) {
  if (!due) return "—";
  return new Date(due).toLocaleString();
}

export default function QueuePage() {
  const [searchParams, setSearchParams] = useSearchParams();
  const [tab, setTab] = useState(searchParams.get("tab") || "expedited");
  const [stats, setStats] = useState<QueueStats | null>(null);
  const [items, setItems] = useState<ArticleListItem[]>([]);
  const [overdueCount, setOverdueCount] = useState(0);
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(true);
  const [products, setProducts] = useState<Product[]>([]);

  const mineOnly = searchParams.get("view") !== "all";
  const productId = Number(searchParams.get("product_id")) || undefined;
  const signalStatus = searchParams.get("signal_status") || undefined;
  const requestedStatus = searchParams.get("status") || undefined;
  const overdueOnly = searchParams.get("overdue") === "true";

  async function load() {
    setLoading(true);
    setError("");
    try {
      const t = TABS.find((x) => x.key === tab);
      const [s, list, overdue, productList] = await Promise.all([
        api.queueStats(mineOnly),
        api.articles({
          queue: requestedStatus || signalStatus || overdueOnly ? undefined : t?.queue,
          status: requestedStatus || t?.status,
          open_only: !(requestedStatus || t?.status),
          mine_only: mineOnly,
          product_id: productId,
          signal_status: signalStatus,
          overdue_only: overdueOnly,
        }),
        api.slaOverdue(),
        api.products(),
      ]);
      setStats(s);
      setItems(list);
      setOverdueCount(overdue.count);
      setProducts(productList);
    } catch (e) {
      setError(String(e));
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    load();
  }, [tab, searchParams.toString()]);

  function setFilter(name: string, value?: string) {
    const next = new URLSearchParams(searchParams);
    if (value) next.set(name, value);
    else next.delete(name);
    setSearchParams(next);
  }

  return (
    <div>
      <div className="page-head">
        <div>
          <h1>{mineOnly ? "My assigned work" : "All reviewer work"}</h1>
          <p className="muted">
            AI ranks and explains; you decide. Nothing potentially reportable is
            discarded silently.
          </p>
        </div>
        <button className="btn" onClick={load}>
          Refresh
        </button>
      </div>

      {overdueCount > 0 && (
        <div className="error" style={{ marginBottom: "1rem" }}>
          <strong>{overdueCount} article(s) past SLA.</strong>{" "}
          <Link to="/ops">Open Ops dashboard</Link> to prioritize breaches.
        </div>
      )}

      <section className="card queue-filters">
        <div className="form-grid">
          <label>
            Assignment scope
            <select
              value={mineOnly ? "mine" : "all"}
              onChange={(e) => setFilter("view", e.target.value)}
            >
              <option value="mine">My work</option>
              <option value="all">All work</option>
            </select>
          </label>
          <label>
            Product
            <select
              value={productId || ""}
              onChange={(e) => setFilter("product_id", e.target.value)}
            >
              <option value="">All products</option>
              {products.map((product) => (
                <option value={product.id} key={product.id}>{product.name}</option>
              ))}
            </select>
          </label>
          <label>
            Signal status
            <select
              value={signalStatus || ""}
              onChange={(e) => setFilter("signal_status", e.target.value)}
            >
              <option value="">All signal states</option>
              <option value="potential_signal">Potential signal</option>
              <option value="confirmed_signal">Confirmed signal</option>
              <option value="rejected_signal">Rejected signal</option>
            </select>
          </label>
          <button
            className="btn"
            onClick={() => setSearchParams(mineOnly ? { view: "mine" } : { view: "all" })}
          >
            Clear filters
          </button>
        </div>
      </section>

      {stats && (
        <div className="stat-row">
          <div className="stat danger">
            <span>Expedited</span>
            <strong>{stats.expedited}</strong>
          </div>
          <div className="stat warn">
            <span>Priority</span>
            <strong>{stats.priority}</strong>
          </div>
          <div className="stat">
            <span>Standard</span>
            <strong>{stats.standard}</strong>
          </div>
          <div className="stat">
            <span>QC sample</span>
            <strong>{stats.qc_sample}</strong>
          </div>
          <div className="stat ok">
            <span>Valid ICSR</span>
            <strong>{stats.valid_icsr}</strong>
          </div>
          <div className="stat muted-stat">
            <span>Not a case</span>
            <strong>{stats.not_case}</strong>
          </div>
          <div className="stat">
            <span>Deferred</span>
            <strong>{stats.deferred ?? 0}</strong>
          </div>
          <div className="stat warn">
            <span>2nd review</span>
            <strong>{stats.second_review ?? 0}</strong>
          </div>
        </div>
      )}

      <div className="tabs">
        {TABS.map((t) => (
          <button
            key={t.key}
            className={tab === t.key ? "tab active" : "tab"}
            onClick={() => {
              setTab(t.key);
              setFilter("tab", t.key);
            }}
          >
            {t.label}
          </button>
        ))}
      </div>

      {error && <div className="error">{error}</div>}
      {loading ? (
        <p className="muted">Loading…</p>
      ) : items.length === 0 ? (
        <div className="empty">
          <p>No articles in this queue.</p>
          <p className="muted">
            Use Admin → Seed demo articles or Run PubMed search to populate.
          </p>
        </div>
      ) : (
        <table className="table">
          <thead>
            <tr>
              <th>SLA due</th>
              <th>Queue</th>
              <th>Score</th>
              <th>PMID</th>
              <th>Title</th>
              <th>Flags</th>
              <th>Signal</th>
            </tr>
          </thead>
          <tbody>
            {items.map((a) => (
              <tr
                key={a.id}
                className={
                  a.sla_due_at && new Date(a.sla_due_at).getTime() < Date.now()
                    ? "row-overdue"
                    : undefined
                }
              >
                <td className={slaClass(a.sla_due_at)}>
                  {formatDue(a.sla_due_at)}
                </td>
                <td>
                  <span className={`pill queue-${a.queue || "none"}`}>
                    {a.queue || a.status}
                  </span>
                </td>
                <td>
                  {a.signal_status !== "not_assessed" ? (
                    <span className={`pill signal-${a.signal_status}`}>{a.signal_status.replace(/_/g, " ")}</span>
                  ) : "—"}
                </td>
                <td>{a.composite != null ? a.composite.toFixed(2) : "—"}</td>
                <td>{a.pmid}</td>
                <td>
                  <Link to={`/articles/${a.id}`}>{a.title}</Link>
                </td>
                <td>
                  {a.hard_rule_triggered && (
                    <span className="pill danger">Hard rule</span>
                  )}
                  {a.sla_due_at &&
                    new Date(a.sla_due_at).getTime() < Date.now() && (
                      <span className="pill danger">Overdue</span>
                    )}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
    </div>
  );
}
