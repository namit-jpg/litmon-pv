import { useCallback, useEffect, useState } from "react";
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

const SUBMISSION_VIEWS: { value: SubmissionStatus; label: string }[] = [
  { value: "pending_decision", label: "Pending decision" },
  { value: "approved_for_submission", label: "Approved" },
  { value: "retained_internally", label: "Retained internally" },
  { value: "submitted", label: "Submitted" },
];

export default function SubmissionPage() {
  const { id } = useParams();
  const articleId = Number(id);
  const [params, setParams] = useSearchParams();
  const status = (params.get("status") || "pending_decision") as SubmissionStatus;
  const [items, setItems] = useState<ArticleListItem[]>([]);
  const [article, setArticle] = useState<ArticleDetail | null>(null);
  const [validation, setValidation] = useState<RegulatoryValidation | null>(null);
  const [record, setRecord] = useState<RegulatoryRecord | null>(null);
  const [versions, setVersions] = useState<ExportPackage[]>([]);
  const [reason, setReason] = useState("");
  const [gateway, setGateway] = useState("");
  const [reference, setReference] = useState("");
  const [acknowledgement, setAcknowledgement] = useState("");
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
        setItems(
          await api.articles({
            submission_status: status,
            review_status: "all",
            open_only: false,
          }),
        );
      }
    } catch (caught) {
      setError(String(caught));
    }
  }, [articleId, status]);

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

  async function decide(decision: SubmissionStatus) {
    await run(async () => {
      await api.regulatoryDecision(articleId, { decision, reason });
      setMessage("The human submission decision was recorded in the audit trail.");
    });
  }

  if (!articleId) {
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
            </button>
          ))}
        </div>
        {error ? <div className="error">{error}</div> : null}
        <section className="card">
          <h2>{humanise(status)}</h2>
          {items.length === 0 ? (
            <p className="muted">No reports in this submission state.</p>
          ) : (
            <table className="table">
              <thead>
                <tr><th>Article</th><th>Product</th><th>Priority</th><th /></tr>
              </thead>
              <tbody>
                {items.map((item) => (
                  <tr key={item.id}>
                    <td>{item.title}<span className="t-sub">PMID {item.pmid}</span></td>
                    <td>{item.product_name || "—"}</td>
                    <td><span className={`pill ${item.priority}`}>{item.priority.toUpperCase()}</span></td>
                    <td><Link className="btn" to={`/submission/${item.id}`}>Open workflow</Link></td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
        </section>
      </div>
    );
  }

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

      <section className="card">
        <h2>Mandatory-field validation</h2>
        {validation ? (
          <>
            <div className="warn-banner">{validation.prototype_notice}</div>
            <table className="table">
              <thead><tr><th>Field</th><th>Required</th><th>Status</th></tr></thead>
              <tbody>
                {validation.fields.map((field) => (
                  <tr key={field.field}>
                    <td>{field.label}</td>
                    <td>{field.required ? "Yes" : "No"}</td>
                    <td><span className={`pill ${field.state === "missing" ? "danger" : ""}`}>{humanise(field.state)}</span></td>
                  </tr>
                ))}
              </tbody>
            </table>
            {validation.blocking_errors.length > 0 ? (
              <ul className="error-list">
                {validation.blocking_errors.map((item) => <li key={item}>{item}</li>)}
              </ul>
            ) : null}
            <button
              className="btn primary no-print"
              disabled={busy || !validation.can_generate}
              onClick={() => run(async () => {
                await api.regulatoryGenerate(articleId);
                setMessage("A new version was generated and stored. Nothing was transmitted.");
              })}
            >
              Generate new XML version
            </button>
          </>
        ) : <p className="muted">Loading validation…</p>}
      </section>

      <section className="card">
        <h2>Stored versions</h2>
        {versions.length === 0 ? <p className="muted">No generated versions yet.</p> : (
          <table className="table">
            <thead><tr><th>Version file</th><th>Generated</th><th /></tr></thead>
            <tbody>{versions.map((version) => (
              <tr key={version.id}>
                <td>{version.filename}</td>
                <td>{new Date(version.created_at).toLocaleString()}</td>
                <td><button className="btn" onClick={() => api.downloadRegulatoryXml(version.id, version.filename)}>Download XML</button></td>
              </tr>
            ))}</tbody>
          </table>
        )}
      </section>

      <section className="card no-print">
        <h2>Submission or storage decision</h2>
        <label>
          Decision rationale
          <textarea value={reason} onChange={(event) => setReason(event.target.value)} rows={3} placeholder="Required: explain why this report should be submitted or retained" />
        </label>
        <div className="row-actions wrap">
          <button className="btn primary" disabled={busy || !reason.trim()} onClick={() => decide("approved_for_submission")}>Approve for submission</button>
          <button className="btn" disabled={busy || !reason.trim()} onClick={() => decide("retained_internally")}>Retain internally</button>
        </div>
      </section>

      {record?.decision === "approved_for_submission" ? (
        <section className="card no-print">
          <h2>Manual gateway record</h2>
          <p className="muted">Download the generated file, upload it outside LitMon-PV, then record the evidence returned by the applicable gateway.</p>
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
            disabled={busy || !gateway || !reference || versions.length === 0}
            onClick={() => run(async () => {
              await api.regulatorySubmission(articleId, {
                gateway,
                submission_reference: reference,
                acknowledgement: acknowledgement || undefined,
              });
              setMessage("The manual gateway reference was recorded. LitMon-PV did not transmit the file.");
            })}
          >
            Record manual submission
          </button>
        </section>
      ) : null}

      {record ? (
        <section className="card">
          <h2>Current regulatory record</h2>
          <p><strong>Decision:</strong> {humanise(record.decision)}</p>
          <p><strong>Reason:</strong> {record.decision_reason || "—"}</p>
          <p><strong>Gateway:</strong> {record.gateway || "Not recorded"}</p>
          <p><strong>Reference:</strong> {record.submission_reference || "Not recorded"}</p>
        </section>
      ) : null}
    </div>
  );
}
