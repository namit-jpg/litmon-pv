import { useCallback, useEffect, useMemo, useState } from "react";
import { Link, useSearchParams } from "react-router-dom";
import {
  ActiveIngredient,
  api,
  ArticleFilters,
  ArticleListItem,
  CLASSIFICATIONS,
  humanise,
  LiteratureSource,
  Product,
  User,
  WorkspaceFolder,
} from "../api";

/** Filters that live in the URL, so a drill-through link is shareable and the
 *  back button behaves. Everything the dashboard emits lands in here. */
const FILTER_KEYS = [
  "folder",
  "product_id",
  "active_ingredient_id",
  "date_from",
  "date_to",
  "literature_source_id",
  "classification",
  "classification_group",
  "screened_only",
  "status_group",
  "signal_status",
  "submission_status",
  "assignee_id",
  "priority",
  "review_status",
  "overdue_only",
  "status",
  "queue",
  "q",
] as const;

const SIGNAL_STATUSES = [
  "potential_signal",
  "confirmed_signal",
  "rejected_signal",
  "not_assessed",
];

const SUBMISSION_STATUSES = [
  "pending_decision",
  "approved_for_submission",
  "retained_internally",
  "submitted",
];

function slaClass(due?: string) {
  if (!due) return "";
  const hours = (new Date(due).getTime() - Date.now()) / 36e5;
  if (hours < 0) return "sla-red";
  if (hours < 24) return "sla-amber";
  return "sla-green";
}

/** Relative due time, the way the wireframe writes it: "−1d 4h", "18h", "3d". */
function formatDue(due?: string): string {
  if (!due) return "—";
  const ms = new Date(due).getTime() - Date.now();
  const overdue = ms < 0;
  const hours = Math.abs(ms) / 36e5;
  const label =
    hours < 24
      ? `${Math.round(hours)}h`
      : `${Math.floor(hours / 24)}d ${Math.round(hours % 24)}h`;
  return overdue ? `−${label}` : label;
}

export default function WorkspacePage() {
  const [params, setParams] = useSearchParams();
  const [folders, setFolders] = useState<WorkspaceFolder[]>([]);
  const [items, setItems] = useState<ArticleListItem[]>([]);
  const [products, setProducts] = useState<Product[]>([]);
  const [ingredients, setIngredients] = useState<ActiveIngredient[]>([]);
  const [sources, setSources] = useState<LiteratureSource[]>([]);
  const [users, setUsers] = useState<User[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");

  const mineOnly = params.get("view") !== "all";
  const folder = params.get("folder") || "";

  /** Read the filter set out of the URL. */
  const filters = useMemo<ArticleFilters>(() => {
    const num = (k: string) => {
      const v = Number(params.get(k));
      return v > 0 ? v : undefined;
    };
    return {
      folder: params.get("folder") || undefined,
      status: params.get("status") || undefined,
      queue: params.get("queue") || undefined,
      product_id: num("product_id"),
      active_ingredient_id: num("active_ingredient_id"),
      date_from: params.get("date_from") || undefined,
      date_to: params.get("date_to") || undefined,
      literature_source_id: num("literature_source_id"),
      classification: params.get("classification") || undefined,
      classification_group:
        params.get("classification_group") === "relevant" ? "relevant" : undefined,
      screened_only: params.get("screened_only") === "true" || undefined,
      status_group:
        params.get("status_group") === "awaiting_review"
          ? "awaiting_review"
          : undefined,
      signal_status: params.get("signal_status") || undefined,
      submission_status: params.get("submission_status") || undefined,
      assignee_id: num("assignee_id"),
      priority: params.get("priority") || undefined,
      review_status:
        (params.get("review_status") as ArticleFilters["review_status"]) || undefined,
      overdue_only: params.get("overdue_only") === "true" || undefined,
      q: params.get("q") || undefined,
      mine_only: mineOnly || undefined,
    };
  }, [params, mineOnly]);

  const load = useCallback(async () => {
    setLoading(true);
    setError("");
    try {
      const [folderData, list] = await Promise.all([
        // Folder counts take the same filters as the list, so the number on a
        // folder always matches the rows you get when you open it.
        api.workspaceFolders({ ...filters, folder: undefined }),
        api.articles(filters),
      ]);
      setFolders(folderData.folders);
      setItems(list);
    } catch (e) {
      setError(String(e));
    } finally {
      setLoading(false);
    }
  }, [filters]);

  useEffect(() => {
    load();
  }, [load]);

  // Reference data changes rarely; fetch it once rather than on every filter.
  useEffect(() => {
    Promise.all([
      api.products(),
      api.activeIngredients(),
      api.literatureSources().catch(() => []),
      api.users().catch(() => []),
    ])
      .then(([p, i, s, u]) => {
        setProducts(p);
        setIngredients(i);
        setSources(s);
        setUsers(u);
      })
      .catch(() => undefined);
  }, []);

  function setFilter(name: string, value?: string) {
    const next = new URLSearchParams(params);
    if (value) next.set(name, value);
    else next.delete(name);
    setParams(next);
  }

  function clearFilters() {
    const next = new URLSearchParams();
    if (!mineOnly) next.set("view", "all");
    if (folder) next.set("folder", folder);
    setParams(next);
  }

  const activeFilterCount = FILTER_KEYS.filter(
    (k) => k !== "folder" && params.get(k)
  ).length;

  /** One filter control. `on` styling mirrors the wireframe's active chips. */
  const select = (
    label: string,
    key: string,
    options: { value: string; label: string }[],
    anyLabel = "Any"
  ) => (
    <span className={`fx${params.get(key) ? " on" : ""}`}>
      <b>{label}</b>
      <select
        aria-label={label}
        value={params.get(key) || ""}
        onChange={(e) => setFilter(key, e.target.value)}
      >
        <option value="">{anyLabel}</option>
        {options.map((o) => (
          <option key={o.value} value={o.value}>
            {o.label}
          </option>
        ))}
      </select>
    </span>
  );

  return (
    <div>
      <div className="shd">
        <span className="eyebrow">Step 9 · User folder and work queue</span>
        <h1>My workspace</h1>
        <p className="sub">
          Folders are workflow states, not severity buckets. Severity is the
          priority column, and it drives the sort order.
        </p>
      </div>

      <div className="row-actions wrap no-print" style={{ marginBottom: "0.9rem" }}>
        <span className={`fx${!mineOnly ? " on" : ""}`}>
          <b>Scope</b>
          <select
            aria-label="Assignment scope"
            value={mineOnly ? "mine" : "all"}
            onChange={(e) => setFilter("view", e.target.value === "all" ? "all" : undefined)}
          >
            <option value="mine">My work</option>
            <option value="all">All work</option>
          </select>
        </span>
        <button className="btn" onClick={load}>
          Refresh
        </button>
        {activeFilterCount > 0 && (
          <button className="btn ghost" onClick={clearFilters}>
            Clear {activeFilterCount} filter{activeFilterCount === 1 ? "" : "s"}
          </button>
        )}
      </div>

      {error && <div className="error">{error}</div>}

      <div className="split">
        <div className="folders">
          <button
            className={`folder${!folder ? " is-active" : ""}`}
            onClick={() => setFilter("folder", undefined)}
          >
            All open work
          </button>
          {folders.map((f) => (
            <button
              key={f.key}
              className={`folder${folder === f.key ? " is-active" : ""}`}
              onClick={() => setFilter("folder", f.key)}
            >
              {f.label}
              <span className="ct">{f.count}</span>
            </button>
          ))}
        </div>

        <div>
          <div className="filters">
            {select(
              "Product",
              "product_id",
              products.map((p) => ({ value: String(p.id), label: p.name }))
            )}
            {select(
              "Ingredient / API",
              "active_ingredient_id",
              ingredients.map((i) => ({ value: String(i.id), label: i.name }))
            )}
            <span className={`fx${params.get("date_from") ? " on" : ""}`}>
              <b>From</b>
              <input
                type="date"
                aria-label="Published from"
                value={params.get("date_from") || ""}
                onChange={(e) => setFilter("date_from", e.target.value)}
              />
            </span>
            <span className={`fx${params.get("date_to") ? " on" : ""}`}>
              <b>To</b>
              <input
                type="date"
                aria-label="Published to"
                value={params.get("date_to") || ""}
                onChange={(e) => setFilter("date_to", e.target.value)}
              />
            </span>
            {select(
              "Source",
              "literature_source_id",
              sources.map((s) => ({ value: String(s.id), label: s.name }))
            )}
            {select(
              "Classification",
              "classification",
              CLASSIFICATIONS.map((c) => ({ value: c, label: humanise(c) }))
            )}
            {select(
              "Signal status",
              "signal_status",
              SIGNAL_STATUSES.map((s) => ({ value: s, label: humanise(s) }))
            )}
            {select(
              "Submission",
              "submission_status",
              SUBMISSION_STATUSES.map((s) => ({ value: s, label: humanise(s) }))
            )}
            {select(
              "Assigned",
              "assignee_id",
              users.map((u) => ({ value: String(u.id), label: u.full_name }))
            )}
            {select("Priority", "priority", [
              { value: "p1", label: "P1" },
              { value: "p2", label: "P2" },
              { value: "p3", label: "P3" },
            ])}
            {select(
              "Review status",
              "review_status",
              [
                { value: "open", label: "Open" },
                { value: "closed", label: "Closed" },
                { value: "all", label: "All" },
              ],
              "Default"
            )}
            <span className={`fx${params.get("q") ? " on" : ""}`}>
              <b>Search</b>
              <input
                type="search"
                aria-label="Search title, PMID or abstract"
                placeholder="Title, PMID…"
                value={params.get("q") || ""}
                onChange={(e) => setFilter("q", e.target.value)}
              />
            </span>
          </div>

          {loading ? (
            <p className="muted" style={{ padding: "1rem" }}>
              Loading…
            </p>
          ) : items.length === 0 ? (
            <div className="empty">
              <p>Nothing in this folder under the current filters.</p>
              <p className="muted">
                {activeFilterCount > 0
                  ? "Clear a filter, or pick another folder."
                  : "Run a search from Product search to bring literature in."}
              </p>
            </div>
          ) : (
            <table className="table">
              <thead>
                <tr>
                  <th>Pri</th>
                  <th>Article</th>
                  <th>Classification</th>
                  <th>Signal</th>
                  <th>Conf.</th>
                  <th>Due</th>
                  <th>Assigned</th>
                </tr>
              </thead>
              <tbody>
                {items.map((a) => (
                  <tr
                    key={a.id}
                    className={
                      a.sla_due_at && new Date(a.sla_due_at).getTime() < Date.now()
                        ? "row-overdue"
                        : undefined
                    }
                  >
                    <td>
                      <span className={`pill ${a.priority}`}>
                        {a.priority.toUpperCase()}
                      </span>
                    </td>
                    <td>
                      <Link to={`/articles/${a.id}`} className="t-title">
                        {a.title}
                      </Link>
                      <span className="t-sub mono muted">
                        PMID {a.pmid} · {a.product_name || "—"} ·{" "}
                        {a.literature_source_name || "source not recorded"}
                      </span>
                    </td>
                    <td>
                      {a.effective_classification ? (
                        <span className="pill">
                          {humanise(a.effective_classification)}
                        </span>
                      ) : (
                        <span className="muted">—</span>
                      )}
                      {a.human_classification &&
                        a.ai_classification !== a.human_classification && (
                          <span className="t-sub mono muted">
                            AI said {humanise(a.ai_classification)}
                          </span>
                        )}
                    </td>
                    <td>
                      {a.signal_status !== "not_assessed" ? (
                        <span className={`pill signal-${a.signal_status}`}>
                          {humanise(a.signal_status)}
                        </span>
                      ) : (
                        <span className="muted">—</span>
                      )}
                    </td>
                    <td className="mono">
                      {a.composite != null ? a.composite.toFixed(2) : "—"}
                    </td>
                    <td className={`mono ${slaClass(a.sla_due_at)}`}>
                      {formatDue(a.sla_due_at)}
                    </td>
                    <td className="mono">
                      {a.assignee_name || (
                        <span className="pill danger">Unassigned</span>
                      )}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
        </div>
      </div>
    </div>
  );
}
