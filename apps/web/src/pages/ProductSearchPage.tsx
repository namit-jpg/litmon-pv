import { useEffect, useRef, useState } from "react";
import {
  api,
  DrugCatalogStatus,
  DrugConcept,
  RunNowResult,
  ScheduleFrequency,
  SearchSchedule,
} from "../api";
import { useToast } from "../toast";

const FREQUENCIES: { value: ScheduleFrequency; label: string }[] = [
  { value: "daily", label: "Daily" },
  { value: "weekly", label: "Weekly" },
  { value: "monthly", label: "Monthly" },
];

const DATE_PRESETS = [
  { days: 7, label: "Last 7 days" },
  { days: 14, label: "Last 14 days" },
  { days: 30, label: "Last 30 days" },
  { days: 90, label: "Last 90 days" },
];

function today(): string {
  return new Date().toISOString().slice(0, 10);
}

function plusDays(n: number): string {
  const d = new Date();
  d.setDate(d.getDate() + n);
  return d.toISOString().slice(0, 10);
}

function formatDateTime(value?: string | null): string {
  if (!value) return "—";
  return new Date(value).toLocaleString();
}

export default function ProductSearchPage() {
  const { toast } = useToast();
  const [drugs, setDrugs] = useState<DrugConcept[]>([]);
  const [selected, setSelected] = useState<Record<string, DrugConcept>>({});
  const [filter, setFilter] = useState("");
  const [loadingDrugs, setLoadingDrugs] = useState(true);
  const [catalog, setCatalog] = useState<DrugCatalogStatus | null>(null);
  const [syncing, setSyncing] = useState(false);

  const [schedules, setSchedules] = useState<SearchSchedule[]>([]);
  const [error, setError] = useState("");
  const [msg, setMsg] = useState("");
  const [busy, setBusy] = useState(false);

  const [days, setDays] = useState<number | "">(30);
  const [dateFrom, setDateFrom] = useState("");
  const [dateTo, setDateTo] = useState("");
  const [maxFetch, setMaxFetch] = useState(30);
  const [runResult, setRunResult] = useState<RunNowResult | null>(null);

  const [frequency, setFrequency] = useState<ScheduleFrequency>("weekly");
  const [endDate, setEndDate] = useState(plusDays(90));

  const debounce = useRef<number | undefined>(undefined);

  const chosen = Object.values(selected);
  const catalogEmpty = !catalog || catalog.total === 0;

  async function loadDrugs(q: string) {
    setLoadingDrugs(true);
    try {
      setDrugs(await api.listDrugs(q));
    } catch (e) {
      setError(String(e));
    } finally {
      setLoadingDrugs(false);
    }
  }

  async function loadCatalog() {
    try {
      setCatalog(await api.drugCatalogStatus());
    } catch {
      // The empty-state card remains the safe fallback if status is unavailable.
      setCatalog(null);
    }
  }

  async function loadSchedules() {
    try {
      setSchedules(await api.searchSchedules());
    } catch (e) {
      setError(String(e));
    }
  }

  useEffect(() => {
    loadCatalog();
    loadDrugs("");
    loadSchedules();
  }, []);

  // Debounced so typing does not fire a request per keystroke.
  useEffect(() => {
    if (debounce.current) window.clearTimeout(debounce.current);
    debounce.current = window.setTimeout(() => loadDrugs(filter.trim()), 220);
    return () => {
      if (debounce.current) window.clearTimeout(debounce.current);
    };
  }, [filter]);

  async function wrap(fn: () => Promise<void>) {
    setBusy(true);
    setError("");
    setMsg("");
    try {
      await fn();
    } catch (e) {
      setError(String(e));
      toast("That action did not complete", "error", String(e));
    } finally {
      setBusy(false);
    }
  }

  function toggle(drug: DrugConcept) {
    setSelected((prev) => {
      const next = { ...prev };
      if (next[drug.rxcui]) delete next[drug.rxcui];
      else next[drug.rxcui] = drug;
      return next;
    });
  }

  const payload = () =>
    chosen.map((d) => ({ name: d.name, rxcui: d.rxcui, tty: d.tty }));

  return (
    <div>
      <div className="page-head">
        <div>
          <h1>Product Search</h1>
          <p className="muted">
            Pick the drugs you want to monitor, then search PubMed now or set it
            to repeat.
          </p>
        </div>
        <button
          className="btn"
          disabled={busy}
          onClick={() =>
            wrap(async () => {
              await Promise.all([
                loadCatalog(),
                loadDrugs(filter.trim()),
                loadSchedules(),
              ]);
            })
          }
        >
          Refresh
        </button>
      </div>

      {error && <div className="error">{error}</div>}
      {msg && <div className="ok-banner">{msg}</div>}

      {catalogEmpty ? (
        <section className="card">
          <h2>Download the drug list</h2>
          <p className="muted">
            The drug list comes from the U.S. National Library of Medicine
            (RxNorm) and has not been downloaded yet. It takes a few seconds and
            needs internet once — after that it works offline.
          </p>
          <button
            className="btn primary"
            disabled={syncing}
            onClick={() =>
              wrap(async () => {
                setSyncing(true);
                try {
                  const s = await api.syncDrugCatalog();
                  setCatalog(s);
                  await loadDrugs("");
                  setMsg(`Downloaded ${s.total.toLocaleString()} drugs.`);
                  toast("Drug list downloaded", "success", `${s.total.toLocaleString()} drugs available offline.`);
                } finally {
                  setSyncing(false);
                }
              })
            }
          >
            {syncing ? "Downloading…" : "Download drug list"}
          </button>
        </section>
      ) : (
        <section className="card">
          <div className="page-head compact">
            <div>
              <h2>Select drugs</h2>
              <p className="muted">
                {chosen.length} selected · showing {drugs.length} of{" "}
                {catalog!.total.toLocaleString()} drugs
                {filter.trim() ? " matching your filter" : ""}
              </p>
            </div>
            <div className="row-actions">
              {chosen.length > 0 && (
                <button className="btn" onClick={() => setSelected({})}>
                  Clear selection
                </button>
              )}
            </div>
          </div>

          <label>
            Filter
            <input
              value={filter}
              onChange={(e) => setFilter(e.target.value)}
              placeholder="Type to search all drugs, e.g. atorvastatin or Lipitor…"
            />
          </label>

          {chosen.length > 0 && (
            <div className="chip-row">
              {chosen.map((d) => (
                <button
                  key={d.rxcui}
                  className="chip"
                  title="Remove from selection"
                  onClick={() => toggle(d)}
                >
                  {d.name} <span aria-hidden="true">×</span>
                </button>
              ))}
            </div>
          )}

          {loadingDrugs ? (
            <p className="muted">Loading…</p>
          ) : drugs.length === 0 ? (
            <p className="muted">No drug matches “{filter.trim()}”.</p>
          ) : (
            <div className="drug-grid">
              {drugs.map((d) => (
                <label
                  key={d.rxcui}
                  className={`drug-option${
                    selected[d.rxcui] ? " is-selected" : ""
                  }`}
                  title={`RxCUI ${d.rxcui}`}
                >
                  <input
                    type="checkbox"
                    checked={!!selected[d.rxcui]}
                    onChange={() => toggle(d)}
                  />
                  <span className="drug-option-name">{d.name}</span>
                  <span className={`pill drug-kind-${d.tty}`}>{d.kind}</span>
                  {d.is_monitored && (
                    <span className="pill ok" title="Already monitored">
                      {d.article_count} found
                    </span>
                  )}
                </label>
              ))}
            </div>
          )}
        </section>
      )}

      <div className="grid-2 search-panels">
        <section className="card">
          <h2>Search now</h2>
          <p className="muted">Run a PubMed search for the selected drugs.</p>
          <label>
            Date window
            <select
              value={days === "" ? "custom" : String(days)}
              onChange={(e) => {
                const v = e.target.value;
                if (v === "custom") {
                  setDays("");
                  setDateFrom(plusDays(-30));
                  setDateTo(today());
                } else {
                  setDays(Number(v));
                }
              }}
            >
              {DATE_PRESETS.map((p) => (
                <option value={p.days} key={p.days}>
                  {p.label}
                </option>
              ))}
              <option value="custom">Custom range…</option>
            </select>
          </label>
          {days === "" && (
            <div className="grid-2">
              <label>
                From
                <input
                  type="date"
                  value={dateFrom}
                  max={dateTo || today()}
                  onChange={(e) => setDateFrom(e.target.value)}
                />
              </label>
              <label>
                To
                <input
                  type="date"
                  value={dateTo}
                  min={dateFrom || undefined}
                  max={today()}
                  onChange={(e) => setDateTo(e.target.value)}
                />
              </label>
            </div>
          )}
          <label>
            Max articles per drug
            <input
              type="number"
              min={1}
              max={200}
              value={maxFetch}
              onChange={(e) => setMaxFetch(Number(e.target.value))}
            />
          </label>
          <button
            className="btn primary"
            disabled={busy || chosen.length === 0}
            onClick={() =>
              wrap(async () => {
                setRunResult(null);
                const res = await api.runSearchNow({
                  drugs: payload(),
                  max_fetch: maxFetch,
                  ...(days === ""
                    ? { date_from: dateFrom, date_to: dateTo }
                    : { days: Number(days) }),
                });
                setRunResult(res);
                setMsg(
                  `Searched ${res.requested} drug(s): ${res.new_articles} new article(s), ${res.failed} failed.`
                );
                toast(
                  res.failed
                    ? `Search finished with ${res.failed} failure(s)`
                    : `${res.new_articles} new article(s) found`,
                  res.failed ? "info" : "success",
                  `${res.requested} drug(s) searched — new items are in your workspace.`
                );
                await Promise.all([loadDrugs(filter.trim()), loadSchedules()]);
              })
            }
          >
            {busy ? "Searching…" : `Search now (${chosen.length})`}
          </button>
          {chosen.length === 0 && (
            <p className="hint">Select at least one drug above.</p>
          )}

          {runResult && (
            <>
              <h3>Result</h3>
              <table className="table">
                <thead>
                  <tr>
                    <th>Drug</th>
                    <th>Status</th>
                    <th>New</th>
                    <th>Hits</th>
                  </tr>
                </thead>
                <tbody>
                  {runResult.results.map((r) => (
                    <tr key={r.product_id}>
                      <td>{r.product_name || r.product_id}</td>
                      <td>
                        <span
                          className={`pill ${
                            r.status === "completed" ? "ok" : "danger"
                          }`}
                        >
                          {r.status}
                        </span>
                        {r.error && <div className="muted">{r.error}</div>}
                      </td>
                      <td>{r.new_articles ?? "—"}</td>
                      <td>{r.hit_count ?? "—"}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </>
          )}
        </section>

        <section className="card">
          <h2>Search automatically</h2>
          <p className="muted">
            Repeat the search on a schedule until the end date. Each run looks
            back far enough to cover the gap since the last one.
          </p>
          <label>
            Frequency
            <select
              value={frequency}
              onChange={(e) => setFrequency(e.target.value as ScheduleFrequency)}
            >
              {FREQUENCIES.map((f) => (
                <option value={f.value} key={f.value}>
                  {f.label}
                </option>
              ))}
            </select>
          </label>
          <label>
            To date
            <input
              type="date"
              value={endDate}
              min={today()}
              onChange={(e) => setEndDate(e.target.value)}
            />
          </label>
          <label>
            Max articles per run
            <input
              type="number"
              min={1}
              max={200}
              value={maxFetch}
              onChange={(e) => setMaxFetch(Number(e.target.value))}
            />
          </label>
          <button
            className="btn primary"
            disabled={busy || chosen.length === 0 || !endDate}
            onClick={() =>
              wrap(async () => {
                const created = await api.createSchedules({
                  drugs: payload(),
                  frequency,
                  end_date: endDate,
                  max_fetch: maxFetch,
                });
                await Promise.all([loadDrugs(filter.trim()), loadSchedules()]);
                setMsg(
                  `Scheduled ${created.length} ${frequency} search(es) until ${endDate}. First run starts within a minute.`
                );
                toast(
                  `${created.length} ${frequency} search(es) scheduled`,
                  "success",
                  `Runs until ${endDate}. First run starts within a minute.`
                );
              })
            }
          >
            Schedule {frequency} ({chosen.length})
          </button>
          <p className="hint">
            A new schedule replaces any existing one for the same drug.
          </p>
        </section>
      </div>

      <section className="card">
        <h2>Scheduled searches</h2>
        {schedules.length === 0 ? (
          <p className="muted">Nothing scheduled yet.</p>
        ) : (
          <table className="table">
            <thead>
              <tr>
                <th>Drug</th>
                <th>Frequency</th>
                <th>Next run</th>
                <th>Last run</th>
                <th>Runs</th>
                <th>Until</th>
                <th>State</th>
                <th></th>
              </tr>
            </thead>
            <tbody>
              {schedules.map((s) => (
                <tr key={s.id}>
                  <td>{s.product_name || s.product_id}</td>
                  <td>{s.frequency}</td>
                  <td>{s.is_active ? formatDateTime(s.next_run_at) : "—"}</td>
                  <td>
                    {formatDateTime(s.last_run_at)}
                    {s.last_status && (
                      <div
                        className={
                          s.last_status === "completed" ? "muted" : "sla-red"
                        }
                      >
                        {s.last_status}
                        {s.last_error ? `: ${s.last_error}` : ""}
                      </div>
                    )}
                  </td>
                  <td>{s.run_count}</td>
                  <td>{s.end_date}</td>
                  <td>
                    <span className={`pill ${s.is_active ? "ok" : ""}`}>
                      {s.is_active ? "active" : "stopped"}
                    </span>
                  </td>
                  <td className="row-actions">
                    {s.is_active ? (
                      <button
                        className="btn"
                        disabled={busy}
                        onClick={() =>
                          wrap(async () => {
                            await api.deleteSchedule(s.id);
                            await loadSchedules();
                            setMsg("Schedule stopped.");
                            toast("Schedule stopped", "success");
                          })
                        }
                      >
                        Stop
                      </button>
                    ) : (
                      <button
                        className="btn"
                        disabled={busy}
                        onClick={() =>
                          wrap(async () => {
                            await api.updateSchedule(s.id, { is_active: true });
                            await loadSchedules();
                            setMsg("Schedule resumed.");
                            toast("Schedule resumed", "success");
                          })
                        }
                      >
                        Resume
                      </button>
                    )}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </section>
    </div>
  );
}
