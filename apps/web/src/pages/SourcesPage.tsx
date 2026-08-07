import { useEffect, useState } from "react";
import { api, LiteratureSource, SourceConnection } from "../api";

export default function SourcesPage() {
  const [sources, setSources] = useState<LiteratureSource[]>([]); const [health, setHealth] = useState<SourceConnection | null>(null); const [error, setError] = useState("");
  const load = async () => { try { setError(""); const [s, h] = await Promise.all([api.literatureSources(), api.sourceConnection()]); setSources(s); setHealth(h); } catch (e) { setError(String(e)); } };
  useEffect(() => { load(); }, []);
  const toggle = async (s: LiteratureSource) => { try { await api.updateLiteratureSource(s.id, { is_enabled: !s.is_enabled }); await load(); } catch (e) { setError(String(e)); } };
  return <div><div className="shd"><span className="eyebrow">Step 2 · Source catalogue</span><h1>Literature sources</h1><p className="sub">A source is separate from its provider and access model. This pilot retrieves only via supported APIs.</p></div>{error && <div className="error">{error}</div>}
    {health && <section className={`card ${health.is_healthy ? "ok-banner" : "warn-banner"}`}><strong>{health.source_name} connection: {health.is_healthy ? "healthy" : "requires attention"}</strong><p className="muted">Last successful call: {health.last_successful_call ? new Date(health.last_successful_call).toLocaleString() : "none recorded"} · {health.failures_last_7d} failure(s) in 7 days · {health.rate_limit_per_second}/s</p></section>}
    <section className="card"><table className="table"><thead><tr><th>Source</th><th>Provider</th><th>Access</th><th>Retrieval</th><th>Articles</th><th>Enabled</th></tr></thead><tbody>{sources.map(s => <tr key={s.id}><td><strong>{s.name}</strong><span className="t-sub">{s.kind}</span></td><td>{s.provider || "—"}</td><td>{s.access_model}</td><td>{s.retrieval || "Not configured"}</td><td>{s.article_count}</td><td><button className="btn" onClick={() => toggle(s)}>{s.is_enabled ? "Enabled" : "Disabled"}</button></td></tr>)}</tbody></table></section></div>;
}
