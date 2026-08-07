import { useCallback, useEffect, useState } from "react";
import { api, EvalResult, Product, ThresholdsConfig } from "../api";

export default function AdminPage() {
  const [products, setProducts] = useState<Product[]>([]);
  const [thresholds, setThresholds] = useState<ThresholdsConfig | null>(null);
  const [exports, setExports] = useState<Record<string, unknown>[]>([]);
  const [evaluation, setEvaluation] = useState<EvalResult | null>(null);
  const [productId, setProductId] = useState<number | "">("");
  const [pmids, setPmids] = useState("");
  const [csvText, setCsvText] = useState("pmid,title,abstract,journal\n");
  const [error, setError] = useState("");
  const [message, setMessage] = useState("");
  const [busy, setBusy] = useState(false);

  const load = useCallback(async () => {
    setError("");
    try {
      const [productRows, config, exportRows] = await Promise.all([
        api.products(),
        api.thresholds(),
        api.exports(),
      ]);
      setProducts(productRows);
      setThresholds(config);
      setExports(exportRows);
      setProductId((current) => current || productRows[0]?.id || "");
    } catch (caught) {
      setError(String(caught));
    }
  }, []);

  useEffect(() => {
    load();
  }, [load]);

  async function run(action: () => Promise<void>) {
    setBusy(true);
    setError("");
    setMessage("");
    try {
      await action();
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
        <span className="eyebrow">Pilot administration</span>
        <h1>Admin tools</h1>
        <p className="sub">
          Runtime inspection, controlled imports, evaluation, and legacy pilot
          exports. Product, source, and schedule configuration now live on their own screens.
        </p>
      </div>
      {message ? <div className="ok-banner">{message}</div> : null}
      {error ? <div className="error">{error}</div> : null}

      <section className="card">
        <h2>Runtime configuration</h2>
        {thresholds ? (
          <div className="stat-row">
            <div className="stat"><span>LLM mode</span><strong>{thresholds.llm_mode || (thresholds.llm_mock ? "mock" : "live")}</strong><small>{thresholds.llm_model}</small></div>
            <div className="stat"><span>Fail-open</span><strong>{thresholds.fail_open_on_llm_error === false ? "OFF" : "ON"}</strong><small>heuristic fallback</small></div>
            <div className="stat"><span>PubMed</span><strong>{thresholds.ncbi_email_configured ? "Configured" : "Needs email"}</strong><small>NCBI E-utilities</small></div>
            <div className="stat"><span>Versions</span><strong>{thresholds.prompt_version}</strong><small>{thresholds.ruleset_version} · {thresholds.threshold_version}</small></div>
          </div>
        ) : <p className="muted">Loading configuration…</p>}
      </section>

      <section className="card">
        <h2>Controlled article imports</h2>
        <label>Product<select value={productId} onChange={(event) => setProductId(Number(event.target.value) || "")}><option value="">Select product</option>{products.map((product) => <option key={product.id} value={product.id}>{product.name}</option>)}</select></label>
        <div className="grid-2">
          <div>
            <label>PMIDs<textarea rows={6} value={pmids} onChange={(event) => setPmids(event.target.value)} placeholder="One PMID per line" /></label>
            <button className="btn" disabled={busy || !productId || !pmids.trim()} onClick={() => run(async () => { await api.importPmids(Number(productId), pmids); setMessage("PMID import completed."); })}>Import PMIDs</button>
          </div>
          <div>
            <label>CSV<textarea rows={6} value={csvText} onChange={(event) => setCsvText(event.target.value)} /></label>
            <button className="btn" disabled={busy || !productId || !csvText.trim()} onClick={() => run(async () => { await api.importCsv(Number(productId), csvText, true); setMessage("CSV import completed."); })}>Import CSV</button>
          </div>
        </div>
      </section>

      <section className="card">
        <h2>Evaluation and legacy pilot exports</h2>
        <div className="row-actions wrap">
          <button className="btn" disabled={busy} onClick={() => run(async () => { const result = await api.evaluation(); setEvaluation(result); setMessage("Gold-label evaluation completed."); })}>Run evaluation</button>
          <button className="btn" disabled={busy} onClick={() => run(async () => { await api.exportIcsr(); setMessage("ICSR handoff package generated."); })}>Generate ICSR handoff</button>
          <button className="btn" disabled={busy || !productId} onClick={() => run(async () => { await api.exportParallel(Number(productId)); setMessage("Parallel-run package generated."); })}>Generate parallel-run package</button>
        </div>
        {evaluation ? <p className="ok-banner">Sensitivity {String(evaluation.sensitivity ?? "—")} · Specificity {String(evaluation.specificity ?? "—")} · TP {evaluation.tp} · FN {evaluation.fn}</p> : null}
      </section>

      <section className="card">
        <h2>Export packages</h2>
        {exports.length === 0 ? <p className="muted">No export packages yet.</p> : (
          <table className="table"><thead><tr><th>File</th><th>Records</th><th>Created</th><th /></tr></thead><tbody>{exports.map((item) => <tr key={String(item.id)}><td>{String(item.filename || "—")}</td><td>{String(item.record_count ?? "—")}</td><td>{item.created_at ? new Date(String(item.created_at)).toLocaleString() : "—"}</td><td><button className="btn ghost" onClick={() => api.downloadExport(Number(item.id), "json")}>Download JSON</button></td></tr>)}</tbody></table>
        )}
      </section>
    </div>
  );
}
