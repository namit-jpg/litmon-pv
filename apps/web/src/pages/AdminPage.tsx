import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { api, EvalResult, ThresholdsConfig } from "../api";

const DATE_PRESETS = [
  { label: "7 days", days: 7 },
  { label: "14 days", days: 14 },
  { label: "30 days", days: 30 },
] as const;

export default function AdminPage() {
  const [products, setProducts] = useState<
    { id: number; name: string; synonyms: string[] }[]
  >([]);
  const [strings, setStrings] = useState<
    { id: number; product_id: number; query_text: string; version: number }[]
  >([]);
  const [runs, setRuns] = useState<Record<string, unknown>[]>([]);
  const [exports, setExports] = useState<Record<string, unknown>[]>([]);
  const [evalResult, setEvalResult] = useState<EvalResult | null>(null);
  const [thresholds, setThresholds] = useState<ThresholdsConfig | null>(null);
  const [pmids, setPmids] = useState("");
  const [csvText, setCsvText] = useState(
    "pmid,title,abstract,journal\n90000010,DrugX rash case report,We report a patient with rash after DrugX.,Demo Journal\n"
  );
  const [msg, setMsg] = useState("");
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  const [searchDays, setSearchDays] = useState(7);
  const [maxFetch, setMaxFetch] = useState(15);
  const [selectedStringId, setSelectedStringId] = useState<number | "">("");

  async function refresh() {
    try {
      const [p, s, r, ex, th] = await Promise.all([
        api.products(),
        api.searchStrings(),
        api.searchRuns(),
        api.exports(),
        api.thresholds(),
      ]);
      setProducts(p);
      setStrings(s);
      setRuns(r);
      setExports(ex);
      setThresholds(th);
      if (selectedStringId === "" && s[0]) {
        setSelectedStringId(s[0].id);
      }
    } catch (e) {
      setError(String(e));
    }
  }

  useEffect(() => {
    refresh();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const productId = products[0]?.id;
  const activeStringId =
    typeof selectedStringId === "number"
      ? selectedStringId
      : strings[0]?.id;

  async function wrap(fn: () => Promise<void>) {
    setBusy(true);
    setError("");
    setMsg("");
    try {
      await fn();
      await refresh();
    } catch (e) {
      setError(String(e));
    } finally {
      setBusy(false);
    }
  }

  const llmMode = thresholds?.llm_mode || (thresholds?.llm_mock ? "mock" : "live");

  return (
    <div>
      <div className="page-head">
        <div>
          <h1>Admin / PV Lead</h1>
          <p className="muted">
            Search, import, evaluation, exports — Phase B/E pilot operations
          </p>
        </div>
      </div>

      {msg && <div className="ok-banner">{msg}</div>}
      {error && <div className="error">{error}</div>}

      <section className="card">
        <h2>Runtime config (read-only)</h2>
        <p className="muted">
          Env-driven; change <code>.env</code> and restart API to switch modes.
          LLM errors <strong>fail open</strong> to heuristic scoring with an
          audit flag (articles are never dropped for model outages).
        </p>
        {thresholds ? (
          <div className="stat-row">
            <div className={`stat ${llmMode === "live" ? "ok" : ""}`}>
              <span>LLM mode</span>
              <strong>
                {llmMode === "live"
                  ? "LIVE"
                  : llmMode === "mock_no_key"
                    ? "MOCK (no key)"
                    : "MOCK"}
              </strong>
              <small className="muted">
                LLM_MOCK={String(thresholds.llm_mock)} · key=
                {thresholds.llm_api_key_configured ? "set" : "missing"}
              </small>
            </div>
            <div className="stat">
              <span>Model</span>
              <strong className="clip-strong">{thresholds.llm_model}</strong>
              <small className="muted">{thresholds.llm_base_url || "—"}</small>
            </div>
            <div
              className={`stat ${
                thresholds.ncbi_email_configured ? "ok" : ""
              }`}
            >
              <span>PubMed NCBI</span>
              <strong>
                {thresholds.ncbi_email_configured ? "email OK" : "set NCBI_EMAIL"}
              </strong>
              <small className="muted">
                API key={thresholds.ncbi_api_key_configured ? "set" : "optional"}
              </small>
            </div>
            <div className="stat">
              <span>Fail-open</span>
              <strong>
                {thresholds.fail_open_on_llm_error !== false ? "ON" : "OFF"}
              </strong>
              <small className="muted">heuristic on LLM error</small>
            </div>
          </div>
        ) : (
          <p className="muted">Loading config…</p>
        )}
      </section>

      <section className="card">
        <h2>Pipeline actions</h2>
        <div className="row-actions wrap">
          <button
            className="btn primary"
            disabled={busy}
            onClick={() =>
              wrap(async () => {
                const res = await api.seedDemo();
                setMsg(`Seeded ${res.seeded} demo articles (offline).`);
              })
            }
          >
            Seed demo articles
          </button>
          <button
            className="btn"
            disabled={busy}
            onClick={() =>
              wrap(async () => {
                const exp = await api.exportIcsr();
                setMsg(
                  `ICSR export #${exp.id}: ${exp.record_count} record(s)`
                );
              })
            }
          >
            Export ICSRs
          </button>
          <button
            className="btn"
            disabled={busy}
            onClick={() =>
              wrap(async () => {
                const exp = await api.exportParallel(productId);
                setMsg(
                  `Parallel-run export #${exp.id}: ${exp.record_count} rows (fill manual columns offline)`
                );
              })
            }
          >
            Export parallel-run
          </button>
          <button
            className="btn"
            disabled={busy}
            onClick={() =>
              wrap(async () => {
                const r = await api.evaluation();
                setEvalResult(r);
                setMsg(
                  `Evaluation: sensitivity=${r.sensitivity} (TP=${r.tp} FN=${r.fn} FP=${r.fp} TN=${r.tn})`
                );
              })
            }
          >
            Run gold evaluation
          </button>
        </div>
      </section>

      <section className="card">
        <h2>Run PubMed search (live E-utilities)</h2>
        <p className="muted">
          Uses NCBI ESearch → EFetch only (no HTML scraping). Requires a real{" "}
          <code>NCBI_EMAIL</code>. Failed runs appear below and can be retried.
        </p>
        {!thresholds?.ncbi_email_configured && (
          <div className="warn-banner">
            <code>NCBI_EMAIL</code> looks unset or still a placeholder. Live
            searches may be rate-limited or rejected.
          </div>
        )}
        <div className="form-grid">
          <label>
            Search string
            <select
              value={activeStringId ?? ""}
              onChange={(e) =>
                setSelectedStringId(
                  e.target.value ? Number(e.target.value) : ""
                )
              }
            >
              {strings.length === 0 && <option value="">None configured</option>}
              {strings.map((s) => (
                <option key={s.id} value={s.id}>
                  #{s.id} · product {s.product_id} · v{s.version}
                </option>
              ))}
            </select>
          </label>
          <label>
            Date window
            <div className="row-actions wrap" style={{ marginTop: 4 }}>
              {DATE_PRESETS.map((p) => (
                <button
                  key={p.days}
                  type="button"
                  className={`btn ${searchDays === p.days ? "primary" : ""}`}
                  onClick={() => setSearchDays(p.days)}
                >
                  {p.label}
                </button>
              ))}
            </div>
          </label>
          <label>
            Max fetch
            <input
              type="number"
              min={1}
              max={200}
              value={maxFetch}
              onChange={(e) => setMaxFetch(Number(e.target.value) || 15)}
            />
          </label>
        </div>
        {activeStringId && (
          <pre className="code-block" style={{ marginTop: "0.75rem" }}>
            {strings.find((s) => s.id === activeStringId)?.query_text}
          </pre>
        )}
        <div className="row-actions wrap" style={{ marginTop: "0.75rem" }}>
          <button
            className="btn primary"
            disabled={busy || !activeStringId}
            onClick={() =>
              wrap(async () => {
                setMsg(
                  `Calling NCBI PubMed E-utilities (last ${searchDays} days)…`
                );
                const run = (await api.runSearch(activeStringId!, {
                  max_fetch: maxFetch,
                  days: searchDays,
                })) as Record<string, unknown>;
                if (String(run.status) === "failed") {
                  setError(
                    `Search #${run.id} failed: ${run.error_message || "unknown"}`
                  );
                } else {
                  setMsg(
                    `Search #${run.id}: ${run.status}, hits=${run.hit_count}, new=${run.new_article_count}, rehit=${run.rehit_count}`
                  );
                }
              })
            }
          >
            Run PubMed search ({searchDays}d)
          </button>
        </div>
        <p className="hint">
          Scheduler CLI: <code>workers/scheduled_search.py --days 7</code>
        </p>
      </section>

      <section className="card">
        <h2>Import PMIDs (PubMed EFetch)</h2>
        <p className="muted">
          Backup path if search fails — paste PMIDs, fetch details via API, score
          &amp; route.
        </p>
        <textarea
          rows={3}
          value={pmids}
          onChange={(e) => setPmids(e.target.value)}
          placeholder="12345678, 23456789"
        />
        <button
          className="btn"
          disabled={busy || !productId || !pmids.trim()}
          onClick={() =>
            wrap(async () => {
              const res = (await api.importPmids(
                productId!,
                pmids
              )) as Record<string, unknown>;
              setMsg(
                `PMID import: created=${res.created}, already_known=${res.already_known}`
              );
            })
          }
        >
          Import PMIDs
        </button>
      </section>

      <section className="card">
        <h2>Import CSV</h2>
        <p className="muted">
          Columns: <code>pmid</code> (required), title, abstract, journal, doi,
          pub_date. Offline-friendly when title/abstract provided.
        </p>
        <textarea
          rows={5}
          value={csvText}
          onChange={(e) => setCsvText(e.target.value)}
        />
        <button
          className="btn"
          disabled={busy || !productId}
          onClick={() =>
            wrap(async () => {
              const res = (await api.importCsv(
                productId!,
                csvText,
                false
              )) as Record<string, unknown>;
              setMsg(
                `CSV import: created=${res.created}, skipped=${res.skipped_existing}`
              );
            })
          }
        >
          Import CSV (no live fetch)
        </button>
      </section>

      {evalResult && (
        <section className="card">
          <h2>Evaluation results (primary KPI: sensitivity)</h2>
          <div className="stat-row">
            <div className="stat ok">
              <span>Sensitivity</span>
              <strong>
                {evalResult.sensitivity != null
                  ? (evalResult.sensitivity * 100).toFixed(1) + "%"
                  : "—"}
              </strong>
            </div>
            <div className="stat">
              <span>Specificity</span>
              <strong>
                {evalResult.specificity != null
                  ? (evalResult.specificity * 100).toFixed(1) + "%"
                  : "—"}
              </strong>
            </div>
            <div className="stat">
              <span>TP / FN</span>
              <strong>
                {evalResult.tp} / {evalResult.fn}
              </strong>
            </div>
            <div className="stat">
              <span>FP / TN</span>
              <strong>
                {evalResult.fp} / {evalResult.tn}
              </strong>
            </div>
          </div>
          {evalResult.missed_cases?.length > 0 && (
            <>
              <h3>Missed cases (FN)</h3>
              <ul>
                {evalResult.missed_cases.map((m) => (
                  <li key={String(m.id)}>
                    {String(m.id)}: {String(m.title)}
                  </li>
                ))}
              </ul>
            </>
          )}
        </section>
      )}

      {thresholds && (
        <section className="card">
          <h2>Threshold / model versions</h2>
          <p className="muted">
            prompt={String(thresholds.prompt_version)} · ruleset=
            {String(thresholds.ruleset_version)} · threshold=
            {String(thresholds.threshold_version)} · QC sample=
            {String(thresholds.auto_clear_qc_sample_rate)}
          </p>
          <pre className="code-block">
            {JSON.stringify(thresholds.bands, null, 2)}
          </pre>
        </section>
      )}

      <section className="card">
        <h2>Export packages</h2>
        {exports.length === 0 ? (
          <p className="muted">None yet</p>
        ) : (
          <table className="table">
            <thead>
              <tr>
                <th>ID</th>
                <th>File</th>
                <th>Records</th>
                <th>Download</th>
              </tr>
            </thead>
            <tbody>
              {exports.map((ex) => (
                <tr key={String(ex.id)}>
                  <td>{String(ex.id)}</td>
                  <td>{String(ex.filename)}</td>
                  <td>{String(ex.record_count)}</td>
                  <td className="row-actions">
                    <button
                      className="btn"
                      onClick={() => api.downloadExport(Number(ex.id), "json")}
                    >
                      JSON
                    </button>
                    <button
                      className="btn"
                      onClick={() => api.downloadExport(Number(ex.id), "csv")}
                    >
                      CSV
                    </button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </section>

      <section className="card">
        <h2>Products</h2>
        <ul>
          {products.map((p) => (
            <li key={p.id}>
              #{p.id} {p.name}{" "}
              <span className="muted">
                synonyms: {(p.synonyms || []).join(", ")}
              </span>
            </li>
          ))}
        </ul>
      </section>

      <section className="card">
        <h2>Search strings</h2>
        {strings.map((s) => (
          <div key={s.id} className="code-block">
            <div className="muted">
              id={s.id} · product={s.product_id} · v{s.version}
            </div>
            <code>{s.query_text}</code>
          </div>
        ))}
      </section>

      <section className="card">
        <h2>Recent search runs</h2>
        {runs.length === 0 ? (
          <p className="muted">No runs yet</p>
        ) : (
          <table className="table">
            <thead>
              <tr>
                <th>ID</th>
                <th>Status</th>
                <th>Window</th>
                <th>Hits</th>
                <th>New</th>
                <th>By</th>
                <th>Error</th>
                <th></th>
              </tr>
            </thead>
            <tbody>
              {runs.map((r) => (
                <tr key={String(r.id)}>
                  <td>
                    <Link to={`/search-runs/${r.id}`}>{String(r.id)}</Link>
                  </td>
                  <td>
                    <span
                      className={
                        r.status === "failed"
                          ? "pill danger"
                          : r.status === "completed"
                            ? "pill ok"
                            : "pill"
                      }
                    >
                      {String(r.status)}
                    </span>
                  </td>
                  <td className="muted">
                    {r.date_from ? String(r.date_from) : "—"} →{" "}
                    {r.date_to ? String(r.date_to) : "—"}
                  </td>
                  <td>{String(r.hit_count)}</td>
                  <td>{String(r.new_article_count)}</td>
                  <td>{String(r.triggered_by || "")}</td>
                  <td className="clip">
                    {r.error_message ? String(r.error_message) : ""}
                  </td>
                  <td className="row-actions">
                    <Link className="btn" to={`/search-runs/${r.id}`}>
                      Detail
                    </Link>
                    {(r.status === "failed" || r.status === "completed") && (
                      <button
                        className="btn"
                        disabled={busy}
                        onClick={() =>
                          wrap(async () => {
                            const next = await api.retrySearchRun(
                              Number(r.id)
                            );
                            setMsg(
                              `Retry of #${r.id} → new run #${next.id} (${next.status})`
                            );
                            if (next.status === "failed") {
                              setError(
                                String(next.error_message || "Retry failed")
                              );
                            }
                          })
                        }
                      >
                        Retry
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
