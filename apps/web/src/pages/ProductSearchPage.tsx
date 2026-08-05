import { useEffect, useMemo, useRef, useState } from "react";
import {
  api,
  DrugConcept,
  Product,
  RunNowResult,
  ScheduleFrequency,
  SearchSchedule,
} from "../api";
import { useAuth } from "../auth";

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
  const { user } = useAuth();
  const canManageProducts = ["pv_lead", "admin"].includes(user?.role || "");

  const [products, setProducts] = useState<Product[]>([]);
  const [selected, setSelected] = useState<number[]>([]);
  const [schedules, setSchedules] = useState<SearchSchedule[]>([]);
  const [error, setError] = useState("");
  const [msg, setMsg] = useState("");
  const [busy, setBusy] = useState(false);

  // Manual search
  const [days, setDays] = useState<number | "">(30);
  const [dateFrom, setDateFrom] = useState("");
  const [dateTo, setDateTo] = useState("");
  const [maxFetch, setMaxFetch] = useState(30);
  const [runResult, setRunResult] = useState<RunNowResult | null>(null);

  // Automated search
  const [frequency, setFrequency] = useState<ScheduleFrequency>("weekly");
  const [endDate, setEndDate] = useState(plusDays(90));

  // Add product (drug picker)
  const [drugQuery, setDrugQuery] = useState("");
  const [drugResults, setDrugResults] = useState<DrugConcept[]>([]);
  const [drugSearching, setDrugSearching] = useState(false);
  const [catalogTotal, setCatalogTotal] = useState<number | null>(null);
  const debounce = useRef<number | undefined>(undefined);

  async function load() {
    setError("");
    try {
      const [p, s] = await Promise.all([api.products(), api.searchSchedules()]);
      setProducts(p);
      setSchedules(s);
    } catch (e) {
      setError(String(e));
    }
  }

  useEffect(() => {
    load();
    api
      .drugCatalogStatus()
      .then((s) => setCatalogTotal(s.total))
      .catch(() => setCatalogTotal(null));
  }, []);

  // Debounced typeahead against the local RxNorm mirror.
  useEffect(() => {
    if (debounce.current) window.clearTimeout(debounce.current);
    const q = drugQuery.trim();
    if (q.length < 2) {
      setDrugResults([]);
      return;
    }
    debounce.current = window.setTimeout(async () => {
      setDrugSearching(true);
      try {
        setDrugResults(await api.searchDrugs(q));
      } catch {
        setDrugResults([]);
      } finally {
        setDrugSearching(false);
      }
    }, 220);
    return () => {
      if (debounce.current) window.clearTimeout(debounce.current);
    };
  }, [drugQuery]);

  const existingNames = useMemo(
    () => new Set(products.map((p) => p.name.toLowerCase())),
    [products]
  );

  async function wrap(fn: () => Promise<void>) {
    setBusy(true);
    setError("");
    setMsg("");
    try {
      await fn();
    } catch (e) {
      setError(String(e));
    } finally {
      setBusy(false);
    }
  }

  function toggle(id: number) {
    setSelected((prev) =>
      prev.includes(id) ? prev.filter((x) => x !== id) : [...prev, id]
    );
  }

  const allSelected = products.length > 0 && selected.length === products.length;

  async function addProduct(drug: DrugConcept) {
    await wrap(async () => {
      const created = await api.createProduct({
        name: drug.name,
        rxcui: drug.rxcui,
        inn: drug.tty === "IN" ? drug.name : undefined,
        brands: drug.tty === "BN" ? [drug.name] : [],
      });
      setDrugQuery("");
      setDrugResults([]);
      await load();
      setSelected((prev) => [...prev, created.id]);
      setMsg(
        `Added "${created.name}" with a starter PubMed query. Review the query before relying on it.`
      );
    });
  }

  return (
    <div>
      <div className="page-head">
        <div>
          <h1>Product Search</h1>
          <p className="muted">
            Monitor products against PubMed — run a search now, or schedule it to
            repeat.
          </p>
        </div>
        <button className="btn" onClick={() => wrap(load)} disabled={busy}>
          Refresh
        </button>
      </div>

      {error && <div className="error">{error}</div>}
      {msg && <div className="ok-banner">{msg}</div>}

      {canManageProducts && (
        <section className="card">
          <h2>Add a product to monitor</h2>
          <p className="muted">
            Search the NLM RxNorm drug catalogue
            {catalogTotal ? ` (${catalogTotal.toLocaleString()} drugs)` : ""}. Showing
            up to 100 matches.
          </p>
          <label>
            Drug name
            <input
              value={drugQuery}
              onChange={(e) => setDrugQuery(e.target.value)}
              placeholder="Start typing, e.g. atorvastatin or Lipitor…"
            />
          </label>
          {drugSearching && <p className="muted">Searching…</p>}
          {drugQuery.trim().length >= 2 &&
            !drugSearching &&
            drugResults.length === 0 && (
              <p className="muted">
                No matches. If the catalogue is empty, sync it from Admin first.
              </p>
            )}
          {drugResults.length > 0 && (
            <div className="drug-results">
              {drugResults.map((d) => {
                const already = existingNames.has(d.name.toLowerCase());
                return (
                  <button
                    key={d.rxcui}
                    className="drug-result"
                    disabled={busy || already}
                    onClick={() => addProduct(d)}
                    title={already ? "Already monitored" : `RxCUI ${d.rxcui}`}
                  >
                    <span className="drug-result-name">{d.name}</span>
                    <span className={`pill drug-kind-${d.tty}`}>{d.kind}</span>
                    {already && <span className="muted">already monitored</span>}
                  </button>
                );
              })}
            </div>
          )}
        </section>
      )}

      <section className="card">
        <div className="page-head compact">
          <div>
            <h2>Select products</h2>
            <p className="muted">
              {selected.length} of {products.length} selected
            </p>
          </div>
          <div className="row-actions">
            <button
              className="btn"
              onClick={() =>
                setSelected(allSelected ? [] : products.map((p) => p.id))
              }
              disabled={products.length === 0}
            >
              {allSelected ? "Clear all" : "Select all"}
            </button>
          </div>
        </div>
        {products.length === 0 ? (
          <div className="empty">
            <p>No products are being monitored yet.</p>
            <p className="muted">
              {canManageProducts
                ? "Add one above to get started."
                : "Ask a PV Lead or Admin to add one."}
            </p>
          </div>
        ) : (
          <div className="product-select-grid">
            {products.map((p) => (
              <label className="product-select" key={p.id}>
                <input
                  type="checkbox"
                  checked={selected.includes(p.id)}
                  onChange={() => toggle(p.id)}
                />
                <span>
                  <strong>{p.name}</strong>
                  {p.active_ingredients?.length > 0 && (
                    <span className="api-tag-row api-tag-row-compact">
                      {p.active_ingredients.map((ai) => (
                        <span className="api-tag" key={ai.id}>
                          {ai.name}
                        </span>
                      ))}
                    </span>
                  )}
                </span>
                {canManageProducts && (
                  <button
                    className="btn ghost product-remove"
                    disabled={busy}
                    title="Stop monitoring this product"
                    onClick={(e) => {
                      e.preventDefault();
                      wrap(async () => {
                        await api.deactivateProduct(p.id);
                        setSelected((prev) => prev.filter((x) => x !== p.id));
                        await load();
                        setMsg(`Stopped monitoring "${p.name}".`);
                      });
                    }}
                  >
                    Remove
                  </button>
                )}
              </label>
            ))}
          </div>
        )}
      </section>

      <div className="grid-2 search-panels">
        <section className="card">
          <h2>Manual search</h2>
          <p className="muted">Run a PubMed search for the selected products now.</p>
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
            Max articles per product
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
            disabled={busy || selected.length === 0}
            onClick={() =>
              wrap(async () => {
                setRunResult(null);
                const res = await api.runSearchNow({
                  product_ids: selected,
                  max_fetch: maxFetch,
                  ...(days === ""
                    ? { date_from: dateFrom, date_to: dateTo }
                    : { days: Number(days) }),
                });
                setRunResult(res);
                setMsg(
                  `Searched ${res.requested} product(s): ${res.new_articles} new article(s), ${res.failed} failed.`
                );
                await load();
              })
            }
          >
            {busy ? "Searching…" : `Search now (${selected.length})`}
          </button>
          {selected.length === 0 && (
            <p className="hint">Select at least one product above.</p>
          )}

          {runResult && (
            <>
              <h3>Result</h3>
              <table className="table">
                <thead>
                  <tr>
                    <th>Product</th>
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
          <h2>Automated search</h2>
          <p className="muted">
            Repeat the search on a schedule until the end date. Each run looks back
            far enough to cover the gap since the last one.
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
            disabled={busy || selected.length === 0 || !endDate}
            onClick={() =>
              wrap(async () => {
                const created = await api.createSchedules({
                  product_ids: selected,
                  frequency,
                  end_date: endDate,
                  max_fetch: maxFetch,
                });
                await load();
                setMsg(
                  `Scheduled ${created.length} ${frequency} search(es) until ${endDate}. First run starts within a minute.`
                );
              })
            }
          >
            Schedule {frequency} search ({selected.length})
          </button>
          <p className="hint">
            A new schedule replaces any existing one for the same product.
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
                <th>Product</th>
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
                            await load();
                            setMsg("Schedule stopped.");
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
                            await load();
                            setMsg("Schedule resumed.");
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
