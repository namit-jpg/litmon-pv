import { useCallback, useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { api, ExceptionSummary, humanise, ScheduleFrequency, SearchSchedule } from "../api";

export default function SchedulePage() {
  const [schedules, setSchedules] = useState<SearchSchedule[]>([]);
  const [exceptions, setExceptions] = useState<ExceptionSummary | null>(null);
  const [error, setError] = useState("");
  const [message, setMessage] = useState("");
  const [busy, setBusy] = useState(false);

  const load = useCallback(async () => {
    setError("");
    try {
      const [scheduleRows, exceptionData] = await Promise.all([
        api.searchSchedules(),
        api.exceptionSummary(),
      ]);
      setSchedules(scheduleRows);
      setExceptions(exceptionData);
    } catch (caught) {
      setError(String(caught));
    }
  }, []);

  useEffect(() => {
    load();
  }, [load]);

  async function act(action: () => Promise<unknown>, success: string) {
    setBusy(true);
    setError("");
    setMessage("");
    try {
      await action();
      setMessage(success);
      await load();
    } catch (caught) {
      setError(String(caught));
    } finally {
      setBusy(false);
    }
  }

  return (
    <div>
      <div className="shd">
        <span className="eyebrow">Search execution and exception control</span>
        <h1>Search &amp; schedule</h1>
        <p className="sub">
          Scheduled PubMed monitoring is persisted per product. Failed or
          incomplete article processing remains visible in the exception queue.
        </p>
      </div>
      <div className="row-actions no-print">
        <Link className="btn primary" to="/product-search">Configure monitoring</Link>
        <button className="btn" disabled={busy} onClick={() => act(api.runDueSchedules, "Due schedules were checked.")}>Run due schedules now</button>
      </div>
      {message ? <div className="ok-banner">{message}</div> : null}
      {error ? <div className="error">{error}</div> : null}

      <section className="card">
        <h2>Schedules</h2>
        {schedules.length === 0 ? <p className="muted">No recurring searches configured.</p> : (
          <table className="table">
            <thead><tr><th>Product</th><th>Frequency</th><th>Next run</th><th>Last result</th><th>Runs</th><th /></tr></thead>
            <tbody>
              {schedules.map((schedule) => (
                <tr key={schedule.id}>
                  <td><strong>{schedule.product_name || `Product #${schedule.product_id}`}</strong><span className="t-sub">Through {schedule.end_date}</span></td>
                  <td>
                    <select
                      aria-label={`${schedule.product_name || "Product"} frequency`}
                      value={schedule.frequency}
                      disabled={busy}
                      onChange={(event) => act(
                        () => api.updateSchedule(schedule.id, { frequency: event.target.value as ScheduleFrequency }),
                        "Schedule frequency updated.",
                      )}
                    >
                      <option value="daily">Daily</option><option value="weekly">Weekly</option><option value="monthly">Monthly</option>
                    </select>
                  </td>
                  <td>{schedule.next_run_at ? new Date(schedule.next_run_at).toLocaleString() : "—"}</td>
                  <td><span className={`pill ${schedule.last_status === "failed" ? "danger" : ""}`}>{humanise(schedule.last_status || "not_run")}</span>{schedule.last_error ? <span className="t-sub">{schedule.last_error}</span> : null}</td>
                  <td>{schedule.run_count}</td>
                  <td><button className="btn ghost" disabled={busy} onClick={() => act(() => api.updateSchedule(schedule.id, { is_active: !schedule.is_active }), schedule.is_active ? "Schedule paused." : "Schedule resumed.")}>{schedule.is_active ? "Pause" : "Resume"}</button></td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </section>

      <section className="card">
        <div className="page-head compact">
          <div><h2>Exception queue</h2><p className="muted">Causes remain itemised until the partner defines exactly what “invalid” means.</p></div>
          <Link className="btn" to="/?view=all&folder=exceptions">Open exception reports</Link>
        </div>
        {exceptions ? (
          <>
            <p><strong>{exceptions.total}</strong> unresolved exception report(s)</p>
            <div className="dashboard-grid">
              {exceptions.causes.map((cause) => (
                <Link className="dashboard-card" to="/?view=all&folder=exceptions" key={cause.cause}>
                  <span>{cause.label}</span><strong>{cause.count}</strong><small>{cause.alerted ? "In-app alert created" : "No recipient was assigned"}</small>
                </Link>
              ))}
            </div>
            <p className="hint">{exceptions.notice}</p>
          </>
        ) : <p className="muted">Loading exception summary…</p>}
      </section>
    </div>
  );
}
