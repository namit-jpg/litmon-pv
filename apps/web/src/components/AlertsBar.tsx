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
          {items.length === 0 ? (
            <p className="muted alerts-empty">No alerts yet.</p>
          ) : (
            <div className="alerts-list">
              {items.slice(0, 12).map((item) => {
                const body = (
                  <div className={`alert-item ${item.read_at ? "read" : "unread"}`}>
                    <div className="alert-item-head">
                      <strong>{item.title}</strong>
                      <span className={`pill ${item.priority === "high" ? "danger" : ""}`}>
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
