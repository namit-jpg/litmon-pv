import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { AlertItem, api } from "../api";

export default function AlertsBar() {
  const [items, setItems] = useState<AlertItem[]>([]);
  const [open, setOpen] = useState(false);

  async function load() {
    try {
      setItems(await api.alerts());
    } catch {
      // The rest of the pilot UI should remain usable if alert refresh fails.
    }
  }

  useEffect(() => {
    load();
    const timer = window.setInterval(load, 15000);
    return () => window.clearInterval(timer);
  }, []);

  const unread = items.filter((item) => !item.read_at).length;
  const high = items.filter((item) => item.priority === "high").length;
  const normal = items.length - high;

  async function markRead(item: AlertItem) {
    if (!item.read_at) await api.readAlert(item.id);
    setOpen(false);
    await load();
  }

  return (
    <div className="alerts-wrap">
      <button
        className="btn alerts-trigger"
        type="button"
        onClick={() => {
          setOpen((value) => !value);
          load();
        }}
        aria-expanded={open}
      >
        Alerts {unread > 0 && <span className="alert-count">{unread}</span>}
      </button>
      {open && (
        <div className="alerts-panel">
          <div className="alerts-head">
            <strong>Assignment alerts</strong>
            {unread > 0 && (
              <button
                className="link-button"
                onClick={async () => {
                  await api.readAllAlerts();
                  await load();
                }}
              >
                Mark all read
              </button>
            )}
          </div>
          {/* The same priority breakdown the inbox shows, so the split is
              legible before the panel is scrolled. Read-only here: the filters
              that would act on it live on the inbox page. */}
          {items.length > 0 && (
            <div className="tally alerts-tally">
              <span className={`pill ${high > 0 ? "crit" : ""}`.trim()}>{high} high</span>
              <span className="pill">{normal} normal</span>
            </div>
          )}
          {items.length === 0 ? (
            <p className="muted alerts-empty">No alerts yet.</p>
          ) : (
            <div className="alerts-list">
              {items.slice(0, 12).map((item) => {
                const body = (
                  <div
                    className={`alert-item ${item.priority === "high" ? "crit" : ""} ${
                      item.read_at ? "read" : "unread"
                    }`}
                  >
                    <div className="alert-item-head">
                      <strong>{item.title}</strong>
                      <span className={`pill ${item.priority === "high" ? "crit" : ""}`.trim()}>
                        {item.priority}
                      </span>
                    </div>
                    <p>{item.message}</p>
                    <small className="muted">
                      {new Date(item.created_at).toLocaleString()}
                    </small>
                  </div>
                );
                return item.article_id ? (
                  <Link
                    key={item.id}
                    to={`/articles/${item.article_id}`}
                    onClick={() => markRead(item)}
                  >
                    {body}
                  </Link>
                ) : (
                  <button
                    key={item.id}
                    className="alert-item-button"
                    onClick={() => markRead(item)}
                  >
                    {body}
                  </button>
                );
              })}
            </div>
          )}
        </div>
      )}
    </div>
  );
}
