import { useCallback, useEffect, useState } from "react";
import { api, AuditEvent, AuditFacets, humanise } from "../api";

type Filters = {
  actor: string;
  entity_type: string;
  action: string;
  created_from: string;
  created_to: string;
};

const EMPTY_FILTERS: Filters = {
  actor: "",
  entity_type: "",
  action: "",
  created_from: "",
  created_to: "",
};

export default function AuditPage() {
  const [events, setEvents] = useState<AuditEvent[]>([]);
  const [facets, setFacets] = useState<AuditFacets>({
    actors: [],
    actions: [],
    entity_types: [],
  });
  const [filters, setFilters] = useState<Filters>(EMPTY_FILTERS);
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);

  const load = useCallback(async () => {
    setError("");
    try {
      const clean = Object.fromEntries(
        Object.entries(filters).filter(([, value]) => Boolean(value)),
      );
      if (filters.created_from) clean.created_from = `${filters.created_from}T00:00:00Z`;
      if (filters.created_to) clean.created_to = `${filters.created_to}T23:59:59Z`;
      const [eventRows, availableFacets] = await Promise.all([
        api.audit(clean),
        api.auditFacets(),
      ]);
      setEvents(eventRows);
      setFacets(availableFacets);
    } catch (caught) {
      setError(String(caught));
    }
  }, [filters]);

  useEffect(() => {
    load();
  }, [load]);

  function update(name: keyof Filters, value: string) {
    setFilters((current) => ({ ...current, [name]: value }));
  }

  async function exportCsv() {
    setBusy(true);
    setError("");
    try {
      await api.downloadAudit({
        actor: filters.actor || undefined,
        entity_type: filters.entity_type || undefined,
        action: filters.action || undefined,
        created_from: filters.created_from ? `${filters.created_from}T00:00:00Z` : undefined,
        created_to: filters.created_to ? `${filters.created_to}T23:59:59Z` : undefined,
      });
    } catch (caught) {
      setError(String(caught));
    } finally {
      setBusy(false);
    }
  }

  return (
    <div>
      <div className="shd">
        <span className="eyebrow">Inspection-ready evidence</span>
        <h1>Audit trail</h1>
        <p className="sub">
          Search, scoring, assignment, classification, tags, human decisions,
          alerts, versions, and manual submission evidence in one timeline.
        </p>
      </div>

      <div className="filters no-print">
        <span className={filters.actor ? "fx on" : "fx"}>
          <b>Actor</b>
          <select value={filters.actor} onChange={(event) => update("actor", event.target.value)}>
            <option value="">Any actor</option>
            {facets.actors.map((actor) => <option key={actor}>{actor}</option>)}
          </select>
        </span>
        <span className={filters.entity_type ? "fx on" : "fx"}>
          <b>Entity</b>
          <select value={filters.entity_type} onChange={(event) => update("entity_type", event.target.value)}>
            <option value="">Any entity</option>
            {facets.entity_types.map((entity) => <option key={entity}>{entity}</option>)}
          </select>
        </span>
        <span className={filters.action ? "fx on" : "fx"}>
          <b>Action</b>
          <select value={filters.action} onChange={(event) => update("action", event.target.value)}>
            <option value="">Any action</option>
            {facets.actions.map((action) => <option key={action}>{action}</option>)}
          </select>
        </span>
        <span className={filters.created_from ? "fx on" : "fx"}>
          <b>From</b>
          <input type="date" value={filters.created_from} onChange={(event) => update("created_from", event.target.value)} />
        </span>
        <span className={filters.created_to ? "fx on" : "fx"}>
          <b>To</b>
          <input type="date" value={filters.created_to} onChange={(event) => update("created_to", event.target.value)} />
        </span>
      </div>

      <div className="row-actions wrap no-print">
        <button className="btn" onClick={load}>Refresh</button>
        <button className="btn ghost" onClick={() => setFilters(EMPTY_FILTERS)}>Clear filters</button>
        <button className="btn primary" disabled={busy} onClick={exportCsv}>Export filtered CSV</button>
      </div>
      {error ? <div className="error">{error}</div> : null}

      <section className="card">
        <table className="table">
          <thead><tr><th>When</th><th>Actor</th><th>Action</th><th>Entity</th><th>Evidence</th></tr></thead>
          <tbody>
            {events.map((event) => (
              <tr key={event.id}>
                <td className="mono">{new Date(event.created_at).toLocaleString()}</td>
                <td>{event.actor}</td>
                <td><span className="pill">{humanise(event.action)}</span></td>
                <td>{event.entity_type}{event.entity_id ? ` #${event.entity_id}` : ""}</td>
                <td><pre className="audit-payload">{JSON.stringify(event.payload, null, 2)}</pre></td>
              </tr>
            ))}
          </tbody>
        </table>
        {events.length === 0 ? <p className="muted">No events match the current filters.</p> : null}
      </section>
    </div>
  );
}
