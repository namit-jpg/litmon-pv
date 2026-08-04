import { useEffect, useState } from "react";
import { Link, useParams } from "react-router-dom";
import { api, ArticleDetail } from "../api";
import { useAuth } from "../auth";

export default function ArticlePage() {
  const { user } = useAuth();
  const { id } = useParams();
  const articleId = Number(id);
  const [article, setArticle] = useState<ArticleDetail | null>(null);
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  const [rationale, setRationale] = useState("");
  const [patient, setPatient] = useState(false);
  const [drug, setDrug] = useState(false);
  const [event, setEvent] = useState(false);
  const [reporter, setReporter] = useState(false);
  const [seriousness, setSeriousness] = useState("");
  const [listedness, setListedness] = useState("");

  async function load() {
    try {
      const a = await api.article(articleId);
      setArticle(a);
      const pre = a.latest_screening?.icsr_precheck as
        | Record<string, { present?: boolean }>
        | undefined;
      if (pre) {
        setPatient(!!pre.identifiable_patient?.present);
        setDrug(!!pre.suspect_drug?.present);
        setEvent(!!pre.adverse_event?.present);
        setReporter(!!pre.identifiable_reporter?.present);
      }
    } catch (e) {
      setError(String(e));
    }
  }

  useEffect(() => {
    load();
  }, [articleId]);

  async function act(action: string) {
    setBusy(true);
    setError("");
    try {
      await api.review(articleId, {
        action,
        rationale,
        identifiable_patient: patient,
        suspect_drug: drug,
        adverse_event: event,
        identifiable_reporter: reporter,
        seriousness: seriousness || null,
        listedness: listedness || null,
      });
      await load();
    } catch (e) {
      setError(String(e));
    } finally {
      setBusy(false);
    }
  }

  async function claim() {
    await api.claim(articleId);
    await load();
  }

  if (!article) {
    return (
      <div>
        <Link to="/">← Queues</Link>
        {error ? <div className="error">{error}</div> : <p>Loading…</p>}
      </div>
    );
  }

  const s = article.latest_screening;
  const t = article.active_triage;
  const canConfirmSignal = ["senior_reviewer", "pv_lead", "admin"].includes(
    user?.role || ""
  );

  return (
    <div className="article-layout">
      <div className="article-main">
        <Link to="/">← Queues</Link>
        <div className="page-head">
          <div>
            <p className="muted">
              PMID {article.pmid}
              {article.journal ? ` · ${article.journal}` : ""}
              {article.pub_date ? ` · ${article.pub_date}` : ""}
            </p>
            <h1>{article.title}</h1>
          </div>
          <div className="row-actions wrap">
            {article.pubmed_url && (
              <a
                className="btn"
                href={article.pubmed_url}
                target="_blank"
                rel="noreferrer"
              >
                Open PubMed
              </a>
            )}
            <button className="btn" onClick={claim}>
              Claim
            </button>
            <button
              className="btn"
              disabled={busy}
              onClick={async () => {
                setBusy(true);
                try {
                  await api.rescore(articleId);
                  await load();
                } catch (e) {
                  setError(String(e));
                } finally {
                  setBusy(false);
                }
              }}
            >
              Rescore
            </button>
            <button
              className="btn"
              disabled={busy}
              onClick={async () => {
                setBusy(true);
                try {
                  await api.recall(articleId, "Recalled from article view");
                  await load();
                } catch (e) {
                  setError(String(e));
                } finally {
                  setBusy(false);
                }
              }}
            >
              Recall to review
            </button>
          </div>
        </div>

        <section className="card">
          <h2>Abstract</h2>
          <p className="abstract">{article.abstract || "No abstract available."}</p>
          {article.authors?.length > 0 && (
            <p className="muted">Authors: {article.authors.join("; ")}</p>
          )}
        </section>

        <section className="card signal-card">
          <div className="page-head compact">
            <div>
              <h2>Signal assessment</h2>
              <p className="muted">
                AI can surface the article; a PV user must set the signal status.
              </p>
            </div>
            <span className={`pill signal-${article.signal_status}`}>
              {article.signal_status.replace(/_/g, " ")}
            </span>
          </div>
          <div className="row-actions wrap">
            <button
              className="btn primary"
              disabled={busy}
              onClick={() => act("mark_potential_signal")}
            >
              Mark potential signal
            </button>
            {canConfirmSignal && (
              <button
                className="btn"
                disabled={busy}
                onClick={() => act("confirm_signal")}
              >
                Confirm signal
              </button>
            )}
            <button
              className="btn ghost"
              disabled={busy}
              onClick={() => act("reject_signal")}
            >
              Reject signal
            </button>
          </div>
        </section>

        <section className="card">
          <h2>ICSR criteria checklist</h2>
          <p className="muted">
            Explicit reviewer completion — not inferred silently (ICH E2D).
          </p>
          <div className="checklist">
            <label>
              <input
                type="checkbox"
                checked={patient}
                onChange={(e) => setPatient(e.target.checked)}
              />
              Identifiable patient
            </label>
            <label>
              <input
                type="checkbox"
                checked={drug}
                onChange={(e) => setDrug(e.target.checked)}
              />
              Suspect drug
            </label>
            <label>
              <input
                type="checkbox"
                checked={event}
                onChange={(e) => setEvent(e.target.checked)}
              />
              Adverse event
            </label>
            <label>
              <input
                type="checkbox"
                checked={reporter}
                onChange={(e) => setReporter(e.target.checked)}
              />
              Identifiable reporter
            </label>
          </div>
          <div className="grid-2">
            <label>
              Seriousness
              <select
                value={seriousness}
                onChange={(e) => setSeriousness(e.target.value)}
              >
                <option value="">—</option>
                <option value="serious">Serious</option>
                <option value="non_serious">Non-serious</option>
                <option value="unknown">Unknown</option>
              </select>
            </label>
            <label>
              Listedness
              <select
                value={listedness}
                onChange={(e) => setListedness(e.target.value)}
              >
                <option value="">—</option>
                <option value="listed">Listed</option>
                <option value="unlisted">Unlisted</option>
                <option value="unknown">Unknown</option>
              </select>
            </label>
          </div>
          <label>
            Rationale
            <textarea
              rows={3}
              value={rationale}
              onChange={(e) => setRationale(e.target.value)}
              placeholder="Document decision reasoning for audit…"
            />
          </label>
          {error && <div className="error">{error}</div>}
          <div className="row-actions wrap">
            <button
              className="btn primary"
              disabled={busy}
              onClick={() => act("confirm_valid_icsr")}
            >
              Confirm — Valid ICSR
            </button>
            <button
              className="btn"
              disabled={busy}
              onClick={() => act("confirm_not_case")}
            >
              Confirm — Not a case
            </button>
            <button
              className="btn"
              disabled={busy}
              onClick={() => act("override_ai")}
            >
              Override AI
            </button>
            <button
              className="btn"
              disabled={busy}
              onClick={() => act("request_second_review")}
            >
              Second review
            </button>
            <button
              className="btn"
              disabled={busy}
              onClick={() => act("defer_full_text")}
            >
              Defer / full text
            </button>
            <button
              className="btn ghost"
              disabled={busy}
              onClick={() => act("recall_to_review")}
            >
              Recall to review
            </button>
          </div>
        </section>

        {article.decisions?.length > 0 && (
          <section className="card">
            <h2>Decision history</h2>
            <ul className="timeline">
              {article.decisions.map((d) => (
                <li key={String(d.id)}>
                  <strong>{String(d.action)}</strong> — {String(d.rationale || "—")}{" "}
                  <span className="muted">{String(d.created_at || "")}</span>
                </li>
              ))}
            </ul>
          </section>
        )}

        {article.audit_events && article.audit_events.length > 0 && (
          <section className="card">
            <h2>Article audit trail</h2>
            <ul className="timeline">
              {article.audit_events.map((e) => (
                <li key={String(e.id)}>
                  <strong>{String(e.action)}</strong> by {String(e.actor)}{" "}
                  <span className="muted">{String(e.created_at || "")}</span>
                </li>
              ))}
            </ul>
          </section>
        )}
      </div>

      <aside className="article-side">
        <section className="card">
          <h2>AI assessment</h2>
          {!s ? (
            <p className="muted">Not scored yet</p>
          ) : (
            <>
              <div className="score-big">{s.composite.toFixed(2)}</div>
              <p className="muted">{s.summary_for_reviewer}</p>
              <div className="dims">
                <div>
                  <span>Product match</span>
                  <strong>{s.product_match.toFixed(2)}</strong>
                </div>
                <div>
                  <span>Event relevance</span>
                  <strong>{s.event_relevance.toFixed(2)}</strong>
                </div>
                <div>
                  <span>ICSR criteria</span>
                  <strong>{s.icsr_criteria_match.toFixed(2)}</strong>
                </div>
              </div>
              <h3>Reason tags</h3>
              <ul className="tags">
                {s.reason_tags?.map((t, i) => (
                  <li key={i}>
                    {t.label}{" "}
                    <span className="muted">({t.confidence.toFixed(2)})</span>
                  </li>
                ))}
              </ul>
              {s.hard_rule_candidates?.length > 0 && (
                <>
                  <h3>Hard rules</h3>
                  <div className="row-actions wrap">
                    {s.hard_rule_candidates.map((h) => (
                      <span key={h} className="pill danger">
                        {h}
                      </span>
                    ))}
                  </div>
                </>
              )}
              <p className="hint">
                Model: {s.model_id} · prompt {s.prompt_version}
                {s.is_mock ? " · mock/heuristic" : ""}
              </p>
            </>
          )}
        </section>

        {t && (
          <section className="card">
            <h2>Routing</h2>
            <p>
              Queue: <strong>{t.queue}</strong>
            </p>
            <p>
              SLA: {t.sla_hours}h · due{" "}
              <strong>{new Date(t.sla_due_at).toLocaleString()}</strong>
            </p>
            <p className="muted">Status: {article.status}</p>
          </section>
        )}
      </aside>
    </div>
  );
}
