import { useEffect, useState } from "react";
import { api, EvalResult } from "../api";

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
  const [thresholds, setThresholds] = useState<Record<string, unknown> | null>(
    null
  );
  const [pmids, setPmids] = useState("");
  const [csvText, setCsvText] = useState(
    "pmid,title,abstract,journal\n90000010,DrugX rash case report,We report a patient with rash after DrugX.,Demo Journal\n"
  );
  const [msg, setMsg] = useState("");
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);

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
    } catch (e) {
      setError(String(e));
    }
  }

  useEffect(() => {
    refresh();
  }, []);

  const productId = products[0]?.id;

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
            disabled={busy || !strings[0]}
            onClick={() =>
              wrap(async () => {
                setMsg("Calling NCBI PubMed E-utilities…");
                const run = (await api.runSearch(strings[0].id, 15)) as Record<
                  string,
                  unknown
                >;
                setMsg(
                  `Search #${run.id}: ${run.status}, hits=${run.hit_count}, new=${run.new_article_count}`
                );
              })
            }
          >
            Run PubMed search
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
        <p className="hint">
          Live PubMed needs <code>NCBI_EMAIL</code>. Scheduler:{" "}
          <code>workers/scheduled_search.py</code>
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
            {String(thresholds.threshold_version)} · llm_mock=
            {String(thresholds.llm_mock)} · QC sample=
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
                <th>Hits</th>
                <th>New</th>
                <th>By</th>
                <th>Query</th>
              </tr>
            </thead>
            <tbody>
              {runs.map((r) => (
                <tr key={String(r.id)}>
                  <td>{String(r.id)}</td>
                  <td>{String(r.status)}</td>
                  <td>{String(r.hit_count)}</td>
                  <td>{String(r.new_article_count)}</td>
                  <td>{String(r.triggered_by || "")}</td>
                  <td className="clip">{String(r.query_snapshot || "")}</td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </section>
    </div>
  );
}
