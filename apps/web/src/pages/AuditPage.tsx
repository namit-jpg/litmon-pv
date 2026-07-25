import { useEffect, useState } from "react";
import { api } from "../api";

export default function AuditPage() {
  const [events, setEvents] = useState<Record<string, unknown>[]>([]);
  const [entityType, setEntityType] = useState("");
  const [error, setError] = useState("");

  async function load() {
    setError("");
    try {
      const list = await api.audit({
        entity_type: entityType || undefined,
      });
      setEvents(list);
    } catch (e) {
      setError(String(e));
    }
  }

  useEffect(() => {
    load();
  }, []);

  return (
    <div>
      <div className="page-head">
        <div>
          <h1>Audit trail</h1>
          <p className="muted">
            Search runs, scores, routes, reviews, imports, and exports —
            inspection-ready log.
          </p>
        </div>
        <button className="btn" onClick={load}>
          Refresh
        </button>
      </div>

      <div className="row-actions wrap" style={{ marginBottom: "1rem" }}>
        <select
          value={entityType}
          onChange={(e) => setEntityType(e.target.value)}
        >
          <option value="">All entity types</option>
          <option value="article">article</option>
          <option value="search_run">search_run</option>
          <option value="product">product</option>
          <option value="export_package">export_package</option>
          <option value="system">system</option>
        </select>
        <button className="btn primary" onClick={load}>
          Filter
        </button>
      </div>

      {error && <div className="error">{error}</div>}

      <table className="table">
        <thead>
          <tr>
            <th>When</th>
            <th>Actor</th>
            <th>Action</th>
            <th>Entity</th>
            <th>Payload</th>
          </tr>
        </thead>
        <tbody>
          {events.map((e) => (
            <tr key={String(e.id)}>
              <td className="muted" style={{ whiteSpace: "nowrap" }}>
                {e.created_at
                  ? new Date(String(e.created_at)).toLocaleString()
                  : "—"}
              </td>
              <td>{String(e.actor)}</td>
              <td>
                <code>{String(e.action)}</code>
              </td>
              <td>
                {String(e.entity_type)}
                {e.entity_id != null ? ` #${e.entity_id}` : ""}
              </td>
              <td className="clip" title={JSON.stringify(e.payload)}>
                {JSON.stringify(e.payload)}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
