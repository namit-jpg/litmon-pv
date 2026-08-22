import { useCallback, useEffect, useMemo, useState } from "react";
import { Link, useParams, useSearchParams } from "react-router-dom";
import {
  api,
  ArticleDetail,
  ArticleListItem,
  ExportPackage,
  humanise,
  RegulatoryRecord,
  RegulatoryValidation,
  SubmissionStatus,
} from "../api";
import { useToast } from "../toast";

const SUBMISSION_VIEWS: { value: SubmissionStatus; label: string }[] = [
  { value: "pending_decision", label: "Pending decision" },
  { value: "approved_for_submission", label: "Approved" },
  { value: "retained_internally", label: "Retained internally" },
  { value: "submitted", label: "Submitted" },
];

/** Field states, in the same three bands the dashboard and inbox use. */
const FIELD_TONE: Record<string, string> = {
  present: "ok",
  missing: "crit",
  not_stated: "warn",
};

function formatDate(value?: string | null) {
  return value ? new Date(value).toLocaleString() : "—";
}

/**
 * A validated field's value, rendered for a table cell. The API types it as
 * `unknown` because the underlying fields are a mix of strings, numbers, dates
 * and lists, so it is narrowed here rather than trusted to be a string.
 */
function formatValue(value: unknown): string {
  if (value == null || value === "") return "—";
  if (Array.isArray(value)) return value.length ? value.join(", ") : "—";
  if (typeof value === "object") return JSON.stringify(value);
  return String(value);
}

export default function SubmissionPage() {
  const { id } = useParams();
  const articleId = Number(id);
  const { toast } = useToast();
  const [params, setParams] = useSearchParams();
  const status = (params.get("status") || "pending_decision") as SubmissionStatus;
  // Every state's list, not just the open tab's: the tab counts have to come
  // from somewhere, and fetching all four once is the same number of requests
  // as fetching four counts, minus a second round-trip when a tab is clicked.
  const [byStatus, setByStatus] = useState<Record<string, ArticleListItem[]>>({});
  const [article, setArticle] = useState<ArticleDetail | null>(null);
  const [validation, setValidation] = useState<RegulatoryValidation | null>(null);
  const [record, setRecord] = useState<RegulatoryRecord | null>(null);
  const [versions, setVersions] = useState<ExportPackage[]>([]);
  const [reason, setReason] = useState("");
  const [gateway, setGateway] = useState("");
  const [reference, setReference] = useState("");
  const [acknowledgement, setAcknowledgement] = useState("");
  // Re-deciding a filed report silently reverts the article out of Submitted,
  // so that path is closed until it is deliberately opened.
  const [reopening, setReopening] = useState(false);
  const [error, setError] = useState("");
  const [message, setMessage] = useState("");
  const [busy, setBusy] = useState(false);

  const load = useCallback(async () => {
    setError("");
    try {
      if (articleId) {
        const [articleData, validationData, recordData, versionData] =
          await Promise.all([
            api.article(articleId),
            api.regulatoryValidate(articleId),
            api.regulatoryRecord(articleId),
            api.regulatoryVersions(articleId),
          ]);
        setArticle(articleData);
        setValidation(validationData);
        setRecord(recordData);
        setVersions(versionData);
        setReason(recordData?.decision_reason || "");
        setGateway(recordData?.gateway || "");
        setReference(recordData?.submission_reference || "");
        setAcknowledgement(recordData?.acknowledgement || "");
      } else {
        const lists = await Promise.all(
          SUBMISSION_VIEWS.map((view) =>
            api.articles({
              submission_status: view.value,
              review_status: "all",
              open_only: false,
            }),
          ),
        );
        setByStatus(
          Object.fromEntries(
            SUBMISSION_VIEWS.map((view, index) => [view.value, lists[index]]),
          ),
        );
      }
    } catch (caught) {
      setError(String(caught));
    }
  }, [articleId]);

  useEffect(() => {
    load();
  }, [load]);

  // Moving to another report must not leave the previous one's banner behind:
  // "recorded in the audit trail" over a different article is a lie.
  useEffect(() => {
    setMessage("");
    setReopening(false);
  }, [articleId]);

  const tally = useMemo(() => {
    const fields = validation?.fields ?? [];
    return {
      present: fields.filter((field) => field.state === "present").length,
      missing: fields.filter((field) => field.state === "missing").length,
      notStated: fields.filter((field) => field.state === "not_stated").length,
    };
  }, [validation]);

  async function run(action: () => Promise<void>) {
    setBusy(true);
    setError("");
    setMessage("");
    try {
      await action();
      await load();
    } catch (caught) {
      setError(String(caught));
      // Surface the failure the same way as a success, so an action never
      // looks like it did nothing.
      toast("That action did not complete", "error", String(caught));
    } finally {
      setBusy(false);
    }
  }

  async function decide(decision: SubmissionStatus) {
    await run(async () => {
      await api.regulatoryDecision(articleId, { decision, reason });
      setMessage("The human submission decision was recorded in the audit trail.");
      toast(
        decision === "approved_for_submission"
          ? "Approved for submission"
          : "Retained internally",
        "success",
        "Recorded in the audit trail with your reason."
      );
      setReason("");
      setReopening(false);
    });
  }

  if (!articleId) {
    const items = byStatus[status] ?? [];
    return (
      <div>
        <div className="shd">
          <span className="eyebrow">Step 14 · Human submission decision</span>
          <h1>Submission &amp; storage</h1>
          <p className="sub">
            Prototype output only. LitMon-PV generates and stores versions; it
            never transmits a report to a regulator.
          </p>
        </div>
        <div className="tabs no-print">
          {SUBMISSION_VIEWS.map((view) => (
            <button
              key={view.value}
              className={status === view.value ? "tab active" : "tab"}
              onClick={() => setParams({ status: view.value })}
            >
              {view.label}
              {/* The count is what makes the tabs a workload view rather than
                  four links you have to open to find out they are empty. */}
              <span className="tab-count">{(byStatus[view.value] ?? []).length}</span>
            </button>
          ))}
        </div>
        {error ? <div className="error">{error}</div> : null}
        <section className="card">
          <div className="card-head">
            <h2>{humanise(status)}</h2>
            <div className="tally">
              <span className="pill">{items.length} reports</span>
              <span className={`pill ${items.some((item) => item.priority === "p1") ? "crit" : ""}`.trim()}>
                {items.filter((item) => item.priority === "p1").length} P1
              </span>
            </div>
          </div>
          {items.length === 0 ? (
            <p className="muted">No reports in this submission state.</p>
          ) : (
            <table className="table title-led">
              {/* Source is left out on purpose: every pilot record comes from
                  PubMed, so the column would cost the title its width and say
                  nothing. It is on the report itself, where it can vary. */}
              <thead>
                <tr>
                  <th>Article</th>
                  <th>Product</th>
                  <th>Classification</th>
                  <th>Signal</th>
                  <th>Assignee</th>
                  <th>Priority</th>
                  <th />
                </tr>
              </thead>
              <tbody>
                {items.map((item) => (
                  <tr key={item.id}>
                    <td>
                      {item.title}
                      <span className="t-sub">
                        PMID {item.pmid}
                        {item.journal ? ` · ${item.journal}` : ""}
                        {item.pub_date ? ` · ${item.pub_date}` : ""}
                      </span>
                    </td>
                    <td>{item.product_name || "—"}</td>
                    <td>
                      {item.effective_classification
                        ? humanise(item.effective_classification)
                        : "—"}
                    </td>
                    <td>
                      <span className={`pill ${item.signal_status === "potential" ? "warn" : ""}`.trim()}>
                        {humanise(item.signal_status)}
                      </span>
                    </td>
                    <td>{item.assignee_name || "Unassigned"}</td>
                    <td><span className={`pill ${item.priority}`}>{item.priority.toUpperCase()}</span></td>
                    <td><Link className="btn" to={`/submission/${item.id}`}>Open</Link></td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
        </section>
      </div>
    );
  }

  const filed = record?.decision === "submitted";
  const approved = record?.decision === "approved_for_submission";
  // The API refuses a gateway filing without a generated package, and it checks
  // the record's own pointer rather than the version list. Gate the button on
  // the same fact so the refusal cannot arrive as a 409 after the click.
  const packageReady = Boolean(record?.latest_export_id);
  const decisionLocked = filed && !reopening;

  return (
    <div>
      <Link className="no-print" to="/submission">← Submission &amp; storage</Link>
      <div className="shd">
        <span className="eyebrow">Detection report #{articleId}</span>
        <h1>Regulatory output</h1>
        <p className="sub">{article?.title || "Loading report…"}</p>
      </div>
      {error ? <div className="error">{error}</div> : null}
      {message ? <div className="ok-banner">{message}</div> : null}

      {/* Which case this is. Without it the page is four cards of regulatory
          machinery with no way to confirm you opened the right report. */}
      {article ? (
        <section className="card">
          <div className="card-head">
            <h2>Case</h2>
            <div className="tally">
              <span className={`pill ${article.priority}`}>{article.priority.toUpperCase()}</span>
              <span className="pill">{humanise(article.submission_status)}</span>
            </div>
          </div>
          <div className="fact-grid">
            <div><span>PMID</span><strong>{article.pmid}</strong></div>
            <div><span>Product</span><strong>{article.product_name || "—"}</strong></div>
            <div><span>Journal</span><strong>{article.journal || "—"}</strong></div>
            <div><span>Published</span><strong>{article.pub_date || "—"}</strong></div>
            <div>
              <span>Classification</span>
              <strong>
                {humanise(
                  article.human_classification || article.ai_classification || "unclassified",
                )}
              </strong>
            </div>
            <div><span>Signal status</span><strong>{humanise(article.signal_status)}</strong></div>
            <div><span>Reviewer</span><strong>{article.assignee_name || "Unassigned"}</strong></div>
            <div><span>Source</span><strong>{article.literature_source_name || "—"}</strong></div>
          </div>
        </section>
      ) : null}

      {/* The four gates between an assessed case and a recorded filing, each
          reporting the state actually stored rather than a step counter. */}
      <section className="card">
        <h2>Where this stands</h2>
        <div className="dashboard-grid">
          <div className={`dashboard-card ${validation ? (validation.can_generate ? "ok" : "crit") : ""}`.trim()}>
            <span>Mandatory fields</span>
            <strong>{validation ? `${tally.present}/${validation.fields.length}` : "—"}</strong>
            <small>{validation?.can_generate ? "Ready to generate" : `${tally.missing} blocking`}</small>
          </div>
          <div className={`dashboard-card ${versions.length ? "ok" : "warn"}`}>
            <span>Package generated</span>
            <strong>{versions.length ? `v${versions.length}` : "None"}</strong>
            <small>{versions.length ? formatDate(versions[0]?.created_at) : "Not generated yet"}</small>
          </div>
          <div className={`dashboard-card ${record && record.decision !== "pending_decision" ? "ok" : "warn"}`}>
            <span>Human decision</span>
            <strong>{record ? humanise(record.decision) : "Pending"}</strong>
            <small>{record ? formatDate(record.updated_at) : "Not recorded"}</small>
          </div>
          <div className={`dashboard-card ${filed ? "ok" : ""}`.trim()}>
            <span>Gateway filing</span>
            <strong>{filed ? "Recorded" : "Not filed"}</strong>
            <small>{filed ? formatDate(record?.submitted_at) : "Filed outside LitMon-PV"}</small>
          </div>
        </div>
      </section>

      <section className="card">
        <div className="card-head">
          <h2>Mandatory-field validation</h2>
          <div className="tally">
            <span className={`pill ${tally.missing > 0 ? "crit" : ""}`.trim()}>{tally.missing} blocking</span>
            <span className={`pill ${tally.notStated > 0 ? "warn" : ""}`.trim()}>{tally.notStated} not stated</span>
            <span className={`pill ${tally.present > 0 ? "ok" : ""}`.trim()}>{tally.present} present</span>
          </div>
        </div>
        {validation ? (
          <>
            <div className="warn-banner">{validation.prototype_notice}</div>
            <table className="table">
              <thead><tr><th>Field</th><th>Value</th><th>Required</th><th>Status</th></tr></thead>
              <tbody>
                {validation.fields.map((field) => (
                  <tr key={field.field}>
                    <td>{field.label}</td>
                    {/* The value the check actually read. Without it a "present"
                        row asks the reviewer to take the validator's word for
                        what is about to be filed. */}
                    <td className={field.value == null || field.value === "" ? "muted" : ""}>
                      {formatValue(field.value)}
                    </td>
                    <td>{field.required ? "Yes" : "No"}</td>
                    <td><span className={`pill ${FIELD_TONE[field.state] || ""}`.trim()}>{humanise(field.state)}</span></td>
                  </tr>
                ))}
              </tbody>
            </table>
            {validation.blocking_errors.length > 0 ? (
              <>
                <ul className="error-list">
                  {validation.blocking_errors.map((item) => <li key={item}>{item}</li>)}
                </ul>
                {/* These fields are filled during the assessment, so a missing
                    one is only actionable on the detection report. */}
                <p className="muted">
                  Missing fields are recorded while assessing the case. Open the
                  detection report, complete them, and record a decision.
                </p>
              </>
            ) : null}
            <div className="row-actions no-print">
              <button
                className="btn primary"
                disabled={busy || !validation.can_generate}
                onClick={() => run(async () => {
                  const pkg = await api.regulatoryGenerate(articleId);
                  setMessage("A new version was generated and stored. Nothing was transmitted.");
                  toast(
                    "XML version generated",
                    "success",
                    `${pkg.filename} — stored, not transmitted.`
                  );
                })}
              >
                Generate new XML version
              </button>
              <Link
                className={validation.can_generate ? "btn" : "btn primary"}
                to={`/articles/${articleId}`}
              >
                Open detection report
              </Link>
            </div>
          </>
        ) : <p className="muted">Loading validation…</p>}
      </section>

      <section className="card">
        <div className="card-head">
          <h2>Stored versions</h2>
          <span className="pill">{versions.length} stored</span>
        </div>
        {versions.length === 0 ? <p className="muted">No generated versions yet.</p> : (
          <table className="table">
            <thead><tr><th>Ver</th><th>Version file</th><th>Records</th><th>Generated</th><th /></tr></thead>
            {/* The API returns newest first, so the version number counts down
                from the total rather than up from the row index. */}
            <tbody>{versions.map((version, index) => (
              <tr key={version.id}>
                <td>
                  v{versions.length - index}
                  {version.id === record?.latest_export_id ? <span className="pill ok">current</span> : null}
                </td>
                <td>{version.filename}</td>
                <td>{version.record_count}</td>
                <td>{formatDate(version.created_at)}</td>
                <td><button className="btn" onClick={() => api.downloadRegulatoryXml(version.id, version.filename)}>Download XML</button></td>
              </tr>
            ))}</tbody>
          </table>
        )}
      </section>

      <section className="card no-print">
        <div className="card-head">
          <h2>Submission or storage decision</h2>
          {record ? <span className="pill">{humanise(record.decision)}</span> : null}
        </div>
        {decisionLocked ? (
          <>
            <p className="muted">
              This report is recorded as filed. Changing the decision moves it
              back out of Submitted and the gateway reference below stops
              describing its current state.
            </p>
            <button className="btn" onClick={() => setReopening(true)}>
              Reopen the decision
            </button>
          </>
        ) : (
          <>
            {filed ? (
              <div className="warn-banner">
                Recording a new decision will move this report out of Submitted.
                The gateway reference already recorded is kept, but it will no
                longer match the report&rsquo;s state.
              </div>
            ) : null}
            <label>
              Decision rationale
              <textarea value={reason} onChange={(event) => setReason(event.target.value)} rows={3} placeholder="Required: explain why this report should be submitted or retained" />
            </label>
            <div className="row-actions wrap">
              <button className="btn primary" disabled={busy || !reason.trim()} onClick={() => decide("approved_for_submission")}>Approve for submission</button>
              <button className="btn" disabled={busy || !reason.trim()} onClick={() => decide("retained_internally")}>Retain internally</button>
              {filed ? <button className="btn ghost" onClick={() => setReopening(false)}>Cancel</button> : null}
            </div>
          </>
        )}
      </section>

      {approved ? (
        <section className="card no-print">
          <h2>Manual gateway record</h2>
          <p className="muted">Download the generated file, upload it outside LitMon-PV, then record the evidence returned by the applicable gateway.</p>
          {!packageReady ? (
            <div className="warn-banner">
              Generate a validated package first — a gateway filing cannot be
              recorded against a report that has no stored version.
            </div>
          ) : null}
          <div className="form-grid">
            <label>
              Gateway
              <select value={gateway} onChange={(event) => setGateway(event.target.value)}>
                <option value="">Select only after the partner confirms the gateway</option>
                <option value="CDSCO portal">CDSCO portal</option>
                <option value="PvPI">PvPI</option>
                <option value="Internal safety system">Internal safety system</option>
                <option value="Third-party gateway">Third-party gateway</option>
              </select>
            </label>
            <label>Submission reference<input value={reference} onChange={(event) => setReference(event.target.value)} /></label>
            <label>Acknowledgement<input value={acknowledgement} onChange={(event) => setAcknowledgement(event.target.value)} /></label>
          </div>
          <button
            className="btn primary"
            disabled={busy || !gateway || !reference || !packageReady}
            onClick={() => run(async () => {
              await api.regulatorySubmission(articleId, {
                gateway,
                submission_reference: reference,
                acknowledgement: acknowledgement || undefined,
              });
              setMessage("The manual gateway reference was recorded. LitMon-PV did not transmit the file.");
              toast(
                "Submission recorded",
                "success",
                `${gateway} · ${reference} — LitMon-PV did not transmit the file.`
              );
            })}
          >
            Record manual submission
          </button>
        </section>
      ) : null}

      {/* Once filed the form above is gone, because the decision it belongs to
          has moved on. The evidence it captured has to stay visible somewhere,
          so it is restated here read-only rather than disappearing with it. */}
      {filed ? (
        <section className="card">
          <div className="card-head">
            <h2>Gateway filing</h2>
            <span className="pill ok">Recorded</span>
          </div>
          <p className="muted">
            Filed manually outside LitMon-PV. The application stored this
            evidence; it did not transmit the file.
          </p>
          <div className="fact-grid">
            <div><span>Gateway</span><strong>{record?.gateway || "—"}</strong></div>
            <div><span>Submission reference</span><strong>{record?.submission_reference || "—"}</strong></div>
            <div><span>Submitted on</span><strong>{formatDate(record?.submitted_at)}</strong></div>
            <div><span>Acknowledgement</span><strong>{record?.acknowledgement || "Not recorded"}</strong></div>
          </div>
        </section>
      ) : null}

      {record ? (
        <section className="card">
          <h2>Current regulatory record</h2>
          <div className="fact-grid">
            <div><span>Decision</span><strong>{humanise(record.decision)}</strong></div>
            <div><span>Gateway</span><strong>{record.gateway || "Not recorded"}</strong></div>
            <div><span>Reference</span><strong>{record.submission_reference || "Not recorded"}</strong></div>
            <div><span>Acknowledgement</span><strong>{record.acknowledgement || "Not recorded"}</strong></div>
            <div><span>Submitted on</span><strong>{formatDate(record.submitted_at)}</strong></div>
            <div><span>Record opened</span><strong>{formatDate(record.created_at)}</strong></div>
            <div><span>Last updated</span><strong>{formatDate(record.updated_at)}</strong></div>
            <div>
              <span>Filed version</span>
              <strong>
                {record.latest_export_id
                  ? versions.find((version) => version.id === record.latest_export_id)?.filename
                    || `Export #${record.latest_export_id}`
                  : "None"}
              </strong>
            </div>
          </div>
          <h3>Reason</h3>
          <p>{record.decision_reason || "—"}</p>
        </section>
      ) : null}
    </div>
  );
}
