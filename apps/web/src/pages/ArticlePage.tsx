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
import { useToast } from "../toast";

// What each decision means once recorded, so the confirmation says what
// happened rather than echoing the button label back.
const DECISION_RESULT: Record<string, string> = {
  confirm_valid_icsr: "Approved for submission — ready to generate the XML.",
  confirm_not_case: "Recorded as not a case and archived.",
  request_second_review: "Sent for second review.",
  defer_full_text: "Deferred pending full text.",
  confirm_signal: "Confirmed as a signal.",
  reject_signal: "Signal rejected.",
};

export default function ArticlePage() {
  const { user } = useAuth();
  const { toast } = useToast();
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
      toast(
        "Decision recorded",
        "success",
        DECISION_RESULT[action] ?? "Saved to the audit trail."
      );
    } catch (e) {
      setError(String(e));
      toast("Decision was not recorded", "error", String(e));
    } finally {
      setBusy(false);
    }
  }

  async function claim() {
    try {
      await api.claim(articleId);
      await load();
      toast("Assigned to you", "success");
    } catch (e) {
      setError(String(e));
      toast("Could not assign this report", "error", String(e));
    }
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
      toast("Classification saved", "success", humanise(classification));
    } catch (e) {
      setError(String(e));
      toast("Classification was not saved", "error", String(e));
    } finally {
      setBusy(false);
    }
  }

  async function saveTags() {
    setBusy(true); setError("");
    try {
      await api.setSignalTags(articleId, signalTags);
      await load();
      toast(
        "Signal tags saved",
        "success",
        signalTags.length ? signalTags.map(humanise).join(", ") : "All tags cleared."
      );
    } catch (e) {
      setError(String(e));
      toast("Signal tags were not saved", "error", String(e));
    } finally { setBusy(false); }
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
  const hasPriorDecision = article.decisions.length > 0;

  return (
    /* Layout follows the scope-matrix depiction: a single column of six
       sections, with AI Summary and AI Classification side by side. Sections
       absent from that sheet — detection context, signal assessment, current
       assessment, the standalone extraction card and the routing aside — are
       folded into the six below rather than kept as separate blocks. */
    <div className="detection-report report-stack">
      <Link className="no-print" to="/">← My workspace</Link>

      {/* 1 · Routing Info. */}
      <section className="card report-routing">
        <div className="page-head compact">
          <div>
            <span className="eyebrow">Detection report #{article.id}</span>
            <h2>Routing Info.</h2>
          </div>
          <div className="row-actions wrap">
            <span className="pill">{humanise(article.status)}</span>
            <span className={`pill ${article.priority}`}>
              {article.priority.toUpperCase()}
            </span>
            <span className={`pill signal-${article.signal_status}`}>
              {humanise(article.signal_status)}
            </span>
          </div>
        </div>
        <div className="routing-grid">
          <div>
            <span>Product</span>
            <strong>{article.product_name || "Not recorded"}</strong>
          </div>
          <div>
            <span>Ingredients / APIs</span>
            <strong>
              {article.active_ingredients.map((i) => i.name).join(", ") ||
                "None tagged"}
            </strong>
          </div>
          <div>
            <span>Literature source</span>
            <strong>{article.literature_source_name || "Not recorded"}</strong>
          </div>
          <div>
            <span>Detected</span>
            <strong>
              {article.search_date
                ? new Date(article.search_date).toLocaleString()
                : "Not recorded"}
            </strong>
          </div>
          <div>
            <span>Assigned reviewer</span>
            <strong>{article.assignee_name || "Unassigned"}</strong>
          </div>
          <div>
            <span>Queue</span>
            <strong>{t ? t.queue : "Not routed"}</strong>
          </div>
          <div>
            <span>Review due</span>
            <strong>
              {t
                ? `${new Date(t.sla_due_at).toLocaleString()} · ${t.sla_hours}h SLA`
                : "—"}
            </strong>
          </div>
          <div>
            <span>Submission status</span>
            <strong>{humanise(article.submission_status)}</strong>
          </div>
        </div>
        {article.search_terms ? (
          <details className="routing-query no-print">
            <summary className="muted">
              Search terms that matched this article
            </summary>
            <pre className="report-query">{article.search_terms}</pre>
          </details>
        ) : null}
      </section>

      {/* 2 · Article Subject — actions on a single line, per the sheet. */}
      <section className="card">
        <h2>Article Subject</h2>
        <h1 className="subject-title">{article.title}</h1>
        <p className="muted">
          PMID {article.pmid}
          {article.journal ? ` · ${article.journal}` : ""}
          {article.pub_date ? ` · ${article.pub_date}` : ""}
        </p>
        <div className="row-actions subject-actions no-print">
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
          <button className="btn" onClick={() => window.print()}>
            Print / save
          </button>
        </div>
      </section>

      {/* 3 · Article Body */}
      <section className="card">
        <h2>Article Body</h2>
        <p className="abstract">
          {article.abstract || "No abstract available."}
        </p>
        {article.authors?.length > 0 && (
          <p className="muted">Authors: {article.authors.join("; ")}</p>
        )}
      </section>

      {/* 4 · AI Summary beside AI Classification. */}
      <div className="report-split">
        <section className="card">
          <h2>AI Summary</h2>
          {!s ? (
            <p className="muted">Not scored yet.</p>
          ) : (
            <>
              <div className="ai-head">
                <div className="score-big">{s.composite.toFixed(2)}</div>
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
              </div>
              <p>{s.summary_for_reviewer}</p>
              {s.relevance_reason ? (
                <p>
                  <strong>Why this was flagged:</strong> {s.relevance_reason}
                </p>
              ) : null}

              <h3>Extracted safety information</h3>
              <div className="extract-grid">
                <div>
                  <span>Indication</span>
                  <strong>{s.indication || "Not stated"}</strong>
                </div>
                <div>
                  <span>Dosage</span>
                  <strong>{s.dosage || "Not stated"}</strong>
                </div>
                <div>
                  <span>Outcome</span>
                  <strong>{s.outcome || "Not stated"}</strong>
                </div>
                <div>
                  <span>Seriousness</span>
                  <strong>{s.seriousness || "Not stated"}</strong>
                </div>
                <div>
                  <span>Country</span>
                  <strong>{s.country_of_occurrence || "Not stated"}</strong>
                </div>
                <div>
                  <span>Reporter</span>
                  <strong>{s.reporter_type || "Not stated"}</strong>
                </div>
                <div className="extract-wide">
                  <span>Concomitant medication</span>
                  <strong>{s.concomitant_medication || "Not stated"}</strong>
                </div>
              </div>

              {s.reason_tags?.length > 0 && (
                <>
                  <h3>Reason tags</h3>
                  <ul className="tags">
                    {s.reason_tags.map((tag, i) => (
                      <li key={i}>
                        {tag.label}{" "}
                        <span className="muted">
                          ({tag.confidence.toFixed(2)})
                        </span>
                      </li>
                    ))}
                  </ul>
                </>
              )}
              {s.hard_rule_candidates?.length > 0 && (
                <>
                  <h3>Hard rules triggered</h3>
                  <div className="row-actions wrap">
                    {s.hard_rule_candidates.map((h) => (
                      <span key={h} className="pill danger">
                        {h}
                      </span>
                    ))}
                  </div>
                </>
              )}
              {s.article_excerpts.length > 0 && (
                <>
                  <h3>Supporting excerpts</h3>
                  <ul className="timeline">
                    {s.article_excerpts.map((excerpt, i) => (
                      <li key={i}>{excerpt}</li>
                    ))}
                  </ul>
                </>
              )}
              {/* One overall confidence is recorded, not one per field, so it
                  is reported once rather than repeated against each value. */}
              <p className="hint">
                Overall extraction confidence{" "}
                {s.confidence != null ? s.confidence.toFixed(2) : "not recorded"}{" "}
                · model {s.model_id} · prompt {s.prompt_version}
                {s.is_mock ? " · mock/heuristic" : ""}
              </p>
            </>
          )}
        </section>

        <section className="card no-print report-classification">
          <h2>AI Classification</h2>
          <label>
            AI proposed
            <input readOnly value={humanise(article.ai_classification)} />
          </label>
          <label>
            Human-confirmed classification
            <select
              value={classification}
              onChange={(e) => setClassification(e.target.value)}
            >
              <option value="">Not yet confirmed</option>
              {CLASSIFICATIONS.map((value) => (
                <option key={value} value={value}>
                  {humanise(value)}
                </option>
              ))}
            </select>
          </label>
          <div className="row-actions">
            <button
              className="btn primary"
              disabled={busy || !classification}
              onClick={saveClassification}
            >
              Save classification
            </button>
          </div>
          <p className="hint">
            The AI proposal is kept as evidence; your confirmation is what the
            record carries forward.
          </p>
        </section>
      </div>

      {/* 5 · Tags */}
      <section className="card no-print">
        <h2>Tags</h2>
        <p className="muted">
          A separate layer from the classification — an article can carry
          several.
        </p>
        <div className="checklist">
          {SIGNAL_TAGS.map((tag) => (
            <label key={tag}>
              <input
                type="checkbox"
                checked={signalTags.includes(tag)}
                onChange={(e) =>
                  setSignalTags((old) =>
                    e.target.checked
                      ? [...old, tag]
                      : old.filter((v) => v !== tag)
                  )
                }
              />
              {humanise(tag)}
            </label>
          ))}
        </div>
        <div className="row-actions">
          <button className="btn" disabled={busy} onClick={saveTags}>
            Save tags
          </button>
        </div>
      </section>

      {/* 6 · Case Assessment — everything here is written by the decision. */}
      <section className="card no-print">
        <h2>Case Assessment</h2>
        <p className="muted">
          Explicit reviewer completion — not inferred silently (ICH E2D).
          Everything in this panel is saved by the decision you record at the
          bottom.
        </p>

        <h3>Case details</h3>
        <p className="muted">
          These become the regulatory submission. Leave a field blank where the
          article does not state it — the export marks it as not stated rather
          than guessing.
        </p>
        <div className="grid-2">
          <label>
            Patient age / range
            <input
              value={patientAgeRange}
              onChange={(e) => setPatientAgeRange(e.target.value)}
              placeholder="e.g. 45 years"
            />
          </label>
          <label>
            Patient sex
            <select
              value={patientSex}
              onChange={(e) => setPatientSex(e.target.value)}
            >
              <option value="">Not stated</option>
              <option value="female">Female</option>
              <option value="male">Male</option>
              <option value="other">Other / as reported</option>
              <option value="unknown">Unknown</option>
            </select>
          </label>
          <label>
            Country of occurrence
            <input
              value={patientCountry}
              onChange={(e) => setPatientCountry(e.target.value)}
              placeholder="As stated in the article"
            />
          </label>
          <label>
            Suspect product(s)
            <input
              value={suspectProducts}
              onChange={(e) => setSuspectProducts(e.target.value)}
              placeholder="Comma-separated"
            />
          </label>
        </div>
        <label>
          Adverse event terms
          <input
            value={eventTerms}
            onChange={(e) => setEventTerms(e.target.value)}
            placeholder="Comma-separated adverse events"
          />
        </label>

        <h3>Reportability criteria</h3>
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
            value={rationale}
            onChange={(e) => setRationale(e.target.value)}
            placeholder="Document decision reasoning for audit…"
          />
        </label>
        <label>
          Supporting document references
          <textarea
            value={supportingDocuments}
            onChange={(e) => setSupportingDocuments(e.target.value)}
            placeholder="One controlled-document name or URL per line"
          />
        </label>

        <h3>Record a decision</h3>
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
        </div>

        <h3>Signal decision</h3>
        <p className="muted">
          The AI can surface an article; a PV user sets the signal status.
        </p>
        <div className="row-actions wrap">
          <button
            className="btn"
            disabled={busy}
            onClick={() => act("mark_potential_signal")}
          >
            Mark potential signal
          </button>
          {canConfirmSignal && (
            <button
              className="btn"
              disabled={busy || !hasPriorDecision}
              title={
                hasPriorDecision
                  ? undefined
                  : "Record a review decision before confirming a signal."
              }
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
          <button
            className="btn ghost"
            disabled={busy}
            onClick={() => act("recall_to_review")}
          >
            Recall to review
          </button>
        </div>
        {canConfirmSignal && !hasPriorDecision ? (
          <p className="hint">
            Confirming a signal needs a recorded review decision first.
          </p>
        ) : null}
      </section>

      {/* Audit history — decisions and system events in one chronological
          trail, so the record reads in order rather than across two cards. */}
      {((article.audit_events?.length ?? 0) > 0 ||
        (article.decisions?.length ?? 0) > 0) && (
        <section className="card">
          <h2>Audit history</h2>
          <ul className="timeline">
            {[
              ...(article.decisions || []).map((d) => ({
                at: String(d.created_at || ""),
                what: `Decision — ${humanise(String(d.action))}`,
                detail: String(d.rationale || ""),
              })),
              ...(article.audit_events || []).map((e) => ({
                at: String(e.created_at || ""),
                what: humanise(String(e.action)),
                detail: `by ${String(e.actor)}`,
              })),
            ]
              .sort((a, b) => (a.at < b.at ? 1 : -1))
              .map((row, i) => (
                <li key={i}>
                  <strong>{row.what}</strong>
                  {row.detail ? ` — ${row.detail}` : ""}{" "}
                  <span className="muted">{row.at}</span>
                </li>
              ))}
          </ul>
        </section>
      )}
    </div>
  );
}
