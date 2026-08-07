import { useEffect, useState } from "react";
import { Link, useParams } from "react-router-dom";
import {
  api,
  ArticleDetail,
  Classification,
  CLASSIFICATIONS,
  humanise,
  SIGNAL_TAGS,
} from "../api";
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
  const [classification, setClassification] = useState("");
  const [signalTags, setSignalTags] = useState<string[]>([]);
  const [patientAgeRange, setPatientAgeRange] = useState("");
  const [patientSex, setPatientSex] = useState("");
  const [patientCountry, setPatientCountry] = useState("");
  const [eventTerms, setEventTerms] = useState("");
  const [suspectProducts, setSuspectProducts] = useState("");
  const [supportingDocuments, setSupportingDocuments] = useState("");

  async function load() {
    try {
      const a = await api.article(articleId);
      setArticle(a);
      setClassification(a.human_classification || "");
      setSignalTags(a.signal_tags || []);
      setPatientCountry(a.latest_screening?.country_of_occurrence || "");
      setSuspectProducts(a.product_name || "");
      const extractedEvents = a.latest_screening?.entities?.events;
      setEventTerms(
        Array.isArray(extractedEvents)
          ? extractedEvents.map(String).join(", ")
          : "",
      );
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
        patient_age_range: patientAgeRange || null,
        patient_sex: patientSex || null,
        patient_country: patientCountry || null,
        event_terms: eventTerms.split(",").map((value) => value.trim()).filter(Boolean),
        suspect_products: suspectProducts.split(",").map((value) => value.trim()).filter(Boolean),
        supporting_documents: supportingDocuments
          .split("\n")
          .map((value) => value.trim())
          .filter(Boolean),
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

  async function saveClassification() {
    if (!classification) return;
    setBusy(true);
    setError("");
    try {
      await api.setClassification(
        articleId,
        classification as Classification,
        rationale,
      );
      await load();
    } catch (e) {
      setError(String(e));
    } finally {
      setBusy(false);
    }
  }

  async function saveTags() {
    setBusy(true); setError("");
    try { await api.setSignalTags(articleId, signalTags); await load(); }
    catch (e) { setError(String(e)); }
    finally { setBusy(false); }
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
  const canConfirmSignal = ["pv_lead", "admin"].includes(
    user?.role || ""
  );

  return (
    <div className="article-layout detection-report">
      <div className="article-main">
        <Link className="no-print" to="/">← My workspace</Link>
        <div className="page-head">
          <div>
            <span className="eyebrow">Step 11 · Literature detection report #{article.id}</span>
            <p className="muted">
              PMID {article.pmid}
              {article.journal ? ` · ${article.journal}` : ""}
              {article.pub_date ? ` · ${article.pub_date}` : ""}
            </p>
            <h1>{article.title}</h1>
            <div className="row-actions wrap">
              <span className="pill">{humanise(article.status)}</span>
              <span className={`pill ${article.priority}`}>{article.priority.toUpperCase()}</span>
              <span className="pill">{humanise(article.submission_status)}</span>
            </div>
            <div className="api-tag-row">
              <strong>{article.product_name || "—"}</strong>
              {article.active_ingredients.length === 0 ? (
                <span className="muted">no APIs tagged</span>
              ) : (
                article.active_ingredients.map((ai) => (
                  <span
                    className="api-tag"
                    key={ai.id}
                    title={
                      `Active Pharmaceutical Ingredient` +
                      (ai.atc_code ? ` · ATC ${ai.atc_code}` : "") +
                      (ai.inn ? ` · INN ${ai.inn}` : "")
                    }
                  >
                    {ai.name}
                    {ai.atc_code ? (
                      <span className="api-tag-atc">{ai.atc_code}</span>
                    ) : null}
                  </span>
                ))
              )}
            </div>
          </div>
          <div className="row-actions wrap no-print">
            <button className="btn primary" onClick={() => window.print()}>
              Print / save report
            </button>
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

        <section className="card">
          <h2>Detection context</h2>
          <div className="grid-2 report-facts">
            <p><strong>Product:</strong> {article.product_name || "Not recorded"}</p>
            <p><strong>Ingredients / APIs:</strong> {article.active_ingredients.map((item) => item.name).join(", ") || "Not recorded"}</p>
            <p><strong>Literature source:</strong> {article.literature_source_name || "Not recorded"}</p>
            <p><strong>Search date:</strong> {article.search_date ? new Date(article.search_date).toLocaleString() : "Not recorded"}</p>
            <p><strong>Assigned reviewer:</strong> {article.assignee_name || "Unassigned"}</p>
            <p><strong>Submission status:</strong> {humanise(article.submission_status)}</p>
          </div>
          <p><strong>Search terms:</strong></p>
          <pre className="report-query">{article.search_terms || "Not recorded (article may have been imported manually)"}</pre>
        </section>

        <section className="card signal-card no-print">
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
          <h2>Current assessment</h2>
          <div className="grid-2 report-facts">
            <p><strong>AI-proposed classification:</strong> {humanise(article.ai_classification)}</p>
            <p><strong>Human-confirmed classification:</strong> {humanise(article.human_classification)}</p>
            <p><strong>Signal status:</strong> {humanise(article.signal_status)}</p>
            <p><strong>Signal tags:</strong> {article.signal_tags.map(humanise).join(", ") || "None"}</p>
          </div>
          {s?.summary_for_reviewer ? <p><strong>AI-generated summary:</strong> {s.summary_for_reviewer}</p> : null}
        </section>

        <section className="card no-print">
          <h2>Classification and signal tags</h2>
          <p className="muted">The AI proposal is preserved as evidence; this is the human workflow verdict and multi-select signal context.</p>
          <div className="grid-2">
            <label>AI proposed classification
              <input readOnly value={humanise(article.ai_classification)} />
            </label>
            <label>Human-confirmed classification
              <select value={classification} onChange={(e) => setClassification(e.target.value)}>
                <option value="">Not yet confirmed</option>
                {CLASSIFICATIONS.map((value) => <option key={value} value={value}>{humanise(value)}</option>)}
              </select>
            </label>
          </div>
          <div className="grid-2">
            <label>
              Patient age / range
              <input value={patientAgeRange} onChange={(e) => setPatientAgeRange(e.target.value)} placeholder="e.g. 45 years" />
            </label>
            <label>
              Patient sex
              <select value={patientSex} onChange={(e) => setPatientSex(e.target.value)}>
                <option value="">Not stated</option>
                <option value="female">Female</option>
                <option value="male">Male</option>
                <option value="other">Other / as reported</option>
                <option value="unknown">Unknown</option>
              </select>
            </label>
            <label>
              Country of occurrence
              <input value={patientCountry} onChange={(e) => setPatientCountry(e.target.value)} placeholder="As stated in the article" />
            </label>
            <label>
              Suspect product(s)
              <input value={suspectProducts} onChange={(e) => setSuspectProducts(e.target.value)} placeholder="Comma-separated" />
            </label>
          </div>
          <label>
            Event terms
            <input value={eventTerms} onChange={(e) => setEventTerms(e.target.value)} placeholder="Comma-separated adverse events" />
          </label>
          <div className="row-actions" style={{ marginBottom: "1rem" }}>
            <button className="btn" disabled={busy || !classification} onClick={saveClassification}>Save classification</button>
          </div>
          <div className="checklist">
            {SIGNAL_TAGS.map((tag) => <label key={tag}>
              <input type="checkbox" checked={signalTags.includes(tag)} onChange={(e) => setSignalTags((old) => e.target.checked ? [...old, tag] : old.filter((v) => v !== tag))} />
              {humanise(tag)}
            </label>)}
          </div>
          <div className="row-actions"><button className="btn" disabled={busy} onClick={saveTags}>Save signal tags</button></div>
        </section>

        {s && <section className="card">
          <h2>Structured extraction</h2>
          <div className="grid-2">
            <p><strong>Indication:</strong> {s.indication || "Not stated"}</p>
            <p><strong>Dosage:</strong> {s.dosage || "Not stated"}</p>
            <p><strong>Outcome:</strong> {s.outcome || "Not stated"}</p>
            <p><strong>Country:</strong> {s.country_of_occurrence || "Not stated"}</p>
            <p><strong>Reporter:</strong> {s.reporter_type || "Not stated"}</p>
            <p><strong>Concomitant medication:</strong> {s.concomitant_medication || "Not stated"}</p>
          </div>
          {s.relevance_reason && <p><strong>Relevance rationale:</strong> {s.relevance_reason}</p>}
          {s.article_excerpts.length > 0 && <><h3>Supporting excerpts</h3><ul className="timeline">{s.article_excerpts.map((excerpt, i) => <li key={i}>{excerpt}</li>)}</ul></>}
        </section>}

        <section className="card no-print">
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
          <label>
            Supporting document references
            <textarea
              rows={2}
              value={supportingDocuments}
              onChange={(e) => setSupportingDocuments(e.target.value)}
              placeholder="One controlled-document name or URL per line"
            />
          </label>
          {error && <div className="error">{error}</div>}
          <div className="row-actions wrap no-print">
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
            <button className="btn" disabled={busy} onClick={() => act("mark_invalid")}>Mark invalid</button>
            <button className="btn" disabled={busy} onClick={() => act("mark_duplicate")}>Mark duplicate</button>
            <button className="btn" disabled={busy} onClick={() => act("mark_not_relevant")}>Mark not relevant</button>
            <button className="btn primary" disabled={busy} onClick={() => act("prepare_for_submission")}>Prepare for submission</button>
            <button className="btn" disabled={busy} onClick={() => act("retain_internally")}>Retain internally</button>
            <button className="btn ghost" disabled={busy} onClick={() => act("close_report")}>Close report</button>
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
                  {Array.isArray(d.supporting_documents) &&
                  d.supporting_documents.length > 0 ? (
                    <span className="t-sub">
                      Supporting: {d.supporting_documents.map(String).join(", ")}
                    </span>
                  ) : null}
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
