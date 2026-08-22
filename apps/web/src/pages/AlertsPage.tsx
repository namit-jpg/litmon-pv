import { useCallback, useEffect, useState } from "react";
import { Link, useSearchParams } from "react-router-dom";
import { AlertItem, api, humanise, Product } from "../api";

/**
 * Alert severity, in the same colour language the dashboard uses. The backend
 * only ever raises `high` or `normal` (see `services/triggers.py`), so this is
 * one band and a default rather than a ladder.
 *
 * `normal` deliberately takes no tone. The obvious alternative — the accent
 * colour — is fern green in the light theme, and green already means "clear" on
 * the dashboard; painting an unread alert with it would say the opposite of
 * what the row is for. Grey says "normal priority", which is the fact.
 */
function priorityTone(priority: string): string {
  return priority === "high" ? "crit" : "";
}

export default function AlertsPage() {
  const [params, setParams] = useSearchParams();
  const [alerts, setAlerts] = useState<AlertItem[]>([]);
  // The tally is counted over the same filters as the list *except* priority,
  // so the counts stay stable while a priority filter is on. Counting the
  // filtered list instead would report "0 normal" the moment you clicked
  // "high", turning the tally into a control that disables itself.
  const [tallyPool, setTallyPool] = useState<AlertItem[]>([]);
  const [products, setProducts] = useState<Product[]>([]);
  const [error, setError] = useState("");
  const unreadOnly = params.get("unread") !== "false";

  const load = useCallback(async () => {
    setError("");
    const shared = {
      unread_only: unreadOnly,
      product_id: Number(params.get("product_id")) || undefined,
      alert_type: params.get("type") || undefined,
      created_from: params.get("from") ? `${params.get("from")}T00:00:00Z` : undefined,
      created_to: params.get("to") ? `${params.get("to")}T23:59:59Z` : undefined,
    };
    try {
      const [listed, pool] = await Promise.all([
        api.alerts({ ...shared, priority: params.get("priority") || undefined }),
        api.alerts(shared),
      ]);
      setAlerts(listed);
      setTallyPool(pool);
    } catch (caught) {
      setError(String(caught));
    }
  }, [params, unreadOnly]);

  useEffect(() => {
    load();
  }, [load]);

  useEffect(() => {
    api.products().then(setProducts).catch(() => undefined);
  }, []);

  function setFilter(name: string, value?: string) {
    const next = new URLSearchParams(params);
    if (value) next.set(name, value);
    else next.delete(name);
    setParams(next);
  }

  async function markRead(id: number) {
    try {
      await api.readAlert(id);
      await load();
    } catch (caught) {
      setError(String(caught));
    }
  }

  const activePriority = params.get("priority") || "";
  const highCount = tallyPool.filter((alert) => alert.priority === "high").length;
  const normalCount = tallyPool.length - highCount;
  const unreadCount = tallyPool.filter((alert) => !alert.read_at).length;

  return (
    <div>
      <div className="shd">
        <span className="eyebrow">Step 7 · Persistent in-app alert inbox</span>
        <h1>Alerts</h1>
        <p className="sub">
          Workflow alerts remain visible until acknowledged and every read
          action is written to the audit trail.
        </p>
      </div>

      <div className="filters no-print">
        <span className={params.get("priority") ? "fx on" : "fx"}>
          <b>Priority</b>
          <select value={params.get("priority") || ""} onChange={(event) => setFilter("priority", event.target.value)}>
            <option value="">Any priority</option>
            <option value="high">High</option>
            <option value="normal">Normal</option>
          </select>
        </span>
        <span className={params.get("product_id") ? "fx on" : "fx"}>
          <b>Product</b>
          <select value={params.get("product_id") || ""} onChange={(event) => setFilter("product_id", event.target.value)}>
            <option value="">Any product</option>
            {products.map((product) => <option key={product.id} value={product.id}>{product.name}</option>)}
          </select>
        </span>
        <span className={params.get("type") ? "fx on" : "fx"}>
          <b>Type</b>
          <input value={params.get("type") || ""} onChange={(event) => setFilter("type", event.target.value)} placeholder="e.g. search_failed" />
        </span>
        <span className={params.get("from") ? "fx on" : "fx"}>
          <b>From</b>
          <input type="date" value={params.get("from") || ""} onChange={(event) => setFilter("from", event.target.value)} />
        </span>
        <span className={params.get("to") ? "fx on" : "fx"}>
          <b>To</b>
          <input type="date" value={params.get("to") || ""} onChange={(event) => setFilter("to", event.target.value)} />
        </span>
      </div>
      <div className="row-actions wrap no-print">
        <label><input type="checkbox" checked={unreadOnly} onChange={(event) => setFilter("unread", event.target.checked ? undefined : "false")} /> Unread only</label>
        <button className="btn" onClick={load}>Refresh</button>
        <button className="btn ghost" onClick={() => setParams({})}>Clear filters</button>
        {alerts.some((alert) => !alert.read_at) ? (
          <button className="btn primary" onClick={async () => { await api.readAllAlerts(); await load(); }}>Mark all read</button>
        ) : null}
      </div>

      {error ? <div className="error">{error}</div> : null}
      <section className="card">
        {/* The priority tally. Each count is also the filter for its own band,
            so the breakdown and the way to act on it are the same control. */}
        <div className="card-head">
          <h2>Inbox</h2>
          <div className="tally">
            <button
              type="button"
              className={`tally-pill crit ${activePriority === "high" ? "on" : ""}`.trim()}
              aria-pressed={activePriority === "high"}
              onClick={() => setFilter("priority", activePriority === "high" ? undefined : "high")}
            >
              {highCount} high
            </button>
            <button
              type="button"
              className={`tally-pill ${activePriority === "normal" ? "on" : ""}`.trim()}
              aria-pressed={activePriority === "normal"}
              onClick={() => setFilter("priority", activePriority === "normal" ? undefined : "normal")}
            >
              {normalCount} normal
            </button>
            <span className="pill">{unreadCount} unread</span>
          </div>
        </div>
        {alerts.length === 0 ? <p className="muted">No alerts under the current filters.</p> : (
          <div className="alert-list">
            {alerts.map((alert) => (
              <div
                key={alert.id}
                className={`alert-i ${priorityTone(alert.priority)} ${alert.read_at ? "" : "unread"}`.trim()}
              >
                {/* The stripe is the fast read; the pill beside the title
                    repeats it in words, so priority never depends on colour
                    alone. */}
                <span className="sev" />
                <div>
                  <h4>
                    {alert.title}
                    <span className={`pill ${alert.priority === "high" ? "crit" : ""}`.trim()}>
                      {humanise(alert.priority)}
                    </span>
                  </h4>
                  <p>{alert.message}</p>
                  <p className="meta">
                    {[
                      humanise(alert.alert_type),
                      new Date(alert.created_at).toLocaleString(),
                      alert.channels?.length ? alert.channels.join(" + ") : null,
                      alert.read_at ? "read" : "unread",
                    ]
                      .filter(Boolean)
                      .join(" · ")}
                  </p>
                </div>
                <div className="row-actions no-print">
                  {alert.article_id ? <Link className="btn ghost" to={`/articles/${alert.article_id}`}>Open report</Link> : null}
                  {!alert.read_at ? <button className="btn" onClick={() => markRead(alert.id)}>Mark read</button> : null}
                </div>
              </div>
            ))}
          </div>
        )}
      </section>
    </div>
  );
}
