import { useCallback, useEffect, useState } from "react";
import { Link, useSearchParams } from "react-router-dom";
import { AlertItem, api, humanise, Product } from "../api";

export default function AlertsPage() {
  const [params, setParams] = useSearchParams();
  const [alerts, setAlerts] = useState<AlertItem[]>([]);
  const [products, setProducts] = useState<Product[]>([]);
  const [error, setError] = useState("");
  const unreadOnly = params.get("unread") !== "false";

  const load = useCallback(async () => {
    setError("");
    try {
      setAlerts(await api.alerts({
        unread_only: unreadOnly,
        priority: params.get("priority") || undefined,
        product_id: Number(params.get("product_id")) || undefined,
        alert_type: params.get("type") || undefined,
        created_from: params.get("from") ? `${params.get("from")}T00:00:00Z` : undefined,
        created_to: params.get("to") ? `${params.get("to")}T23:59:59Z` : undefined,
      }));
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
        {alerts.length === 0 ? <p className="muted">No alerts under the current filters.</p> : (
          <ul className="timeline alert-list">
            {alerts.map((alert) => (
              <li key={alert.id}>
                <div className="page-head compact">
                  <div>
                    <div className="row-actions wrap">
                      <span className={`pill ${alert.priority === "high" ? "danger" : ""}`}>{humanise(alert.priority)}</span>
                      <strong>{alert.title}</strong>
                    </div>
                    <p>{alert.message}</p>
                    <span className="muted">{humanise(alert.alert_type)} · {new Date(alert.created_at).toLocaleString()}</span>
                  </div>
                  <div className="row-actions no-print">
                    {alert.article_id ? <Link className="btn ghost" to={`/articles/${alert.article_id}`}>Open report</Link> : null}
                    {!alert.read_at ? <button className="btn" onClick={() => markRead(alert.id)}>Mark read</button> : null}
                  </div>
                </div>
              </li>
            ))}
          </ul>
        )}
      </section>
    </div>
  );
}
