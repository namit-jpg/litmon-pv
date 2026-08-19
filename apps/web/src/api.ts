const API_BASE = import.meta.env.VITE_API_BASE || "";

let token: string | null = localStorage.getItem("litmon_token");

export function setToken(t: string | null) {
  token = t;
}

/** Called when the server rejects our token, so the app can clear the session. */
let sessionExpiredHandler: () => void = () => {};

export function onSessionExpiredHandler(fn: () => void) {
  sessionExpiredHandler = fn;
}

function onSessionExpired() {
  token = null;
  localStorage.removeItem("litmon_token");
  localStorage.removeItem("litmon_user");
  sessionExpiredHandler();
}

/** Parse FastAPI error bodies into a short operator-facing message. */
export function formatApiError(raw: string, fallback = "Request failed"): string {
  if (!raw) return fallback;
  try {
    const j = JSON.parse(raw);
    const d = j?.detail;
    if (typeof d === "string") return d;
    if (d && typeof d === "object" && d.message) {
      const retry = d.retryable ? " (retryable)" : "";
      return `${d.message}${retry}`;
    }
    if (Array.isArray(d)) {
      return d.map((x) => x.msg || JSON.stringify(x)).join("; ");
    }
    if (j?.message) return String(j.message);
  } catch {
    /* not JSON */
  }
  return raw.length > 400 ? raw.slice(0, 400) + "…" : raw;
}

async function request<T>(path: string, init: RequestInit = {}): Promise<T> {
  const headers = new Headers(init.headers || {});
  if (token) headers.set("Authorization", `Bearer ${token}`);
  if (!(init.body instanceof FormData) && init.body && !headers.has("Content-Type")) {
    headers.set("Content-Type", "application/json");
  }
  const res = await fetch(`${API_BASE}${path}`, { ...init, headers });
  if (!res.ok) {
    const text = await res.text();
    // An expired token 401s on every endpoint, not just login. Without this the
    // page keeps showing the cached user next to "Invalid credentials", giving
    // no hint that signing in again is the fix.
    if (res.status === 401 && token) {
      onSessionExpired();
      throw new Error("Your session expired. Please sign in again.");
    }
    throw new Error(formatApiError(text, res.statusText));
  }
  if (res.status === 204) return undefined as T;
  const ct = res.headers.get("content-type") || "";
  if (ct.includes("application/json")) return res.json();
  return (await res.text()) as T;
}

export type User = {
  id: number;
  email: string;
  full_name: string;
  role: string;
  presence_status: "offline" | "available" | "busy";
  capacity_limit: number;
  active_work_count: number;
};

export type Presence = {
  user_id: number;
  status: "offline" | "available" | "busy";
  capacity_limit: number;
  active_work_count: number;
  available_capacity: number;
};

/** A drug from the NLM RxNorm catalogue, offered in the product picker. */
export type DrugConcept = {
  rxcui: string;
  name: string;
  /** RxNorm term type: IN ingredient, MIN combination, BN brand. */
  tty: string;
  /** Human-readable form of `tty`. */
  kind: string;
  /** Whether this drug is already being searched. */
  is_monitored: boolean;
  product_id?: number | null;
  article_count: number;
};

/** A drug the user picked. The backing record is created server-side. */
export type DrugRef = {
  name: string;
  rxcui?: string;
  tty?: string;
};

export type DrugCatalogStatus = {
  total: number;
  last_synced_at?: string | null;
};

export type ScheduleFrequency = "daily" | "weekly" | "monthly";

export type SearchSchedule = {
  id: number;
  product_id: number;
  product_name?: string | null;
  frequency: ScheduleFrequency;
  end_date: string;
  lookback_days: number;
  max_fetch: number;
  is_active: boolean;
  next_run_at?: string | null;
  last_run_at?: string | null;
  last_status?: string | null;
  last_error?: string | null;
  run_count: number;
  created_by?: string | null;
};

export type RunNowResult = {
  requested: number;
  succeeded: number;
  failed: number;
  new_articles: number;
  results: {
    product_id: number;
    product_name?: string;
    status: string;
    search_run_id?: number;
    hit_count?: number;
    new_articles?: number;
    rehits?: number;
    error?: string;
  }[];
};

/** An Active Pharmaceutical Ingredient (API) tag. */
export type ActiveIngredient = {
  id: number;
  name: string;
  inn?: string | null;
  atc_code?: string | null;
  unii?: string | null;
  is_active: boolean;
};

export type Product = {
  id: number;
  name: string;
  inn?: string | null;
  brands: string[];
  synonyms: string[];
  atc_code?: string | null;
  /** Marketing authorisation holder — a licence fact, not a molecule fact. */
  mah?: string | null;
  /** ISO country codes the product is sold in. */
  markets: string[];
  is_active: boolean;
  primary_reviewer_id?: number | null;
  active_ingredients: ActiveIngredient[];
};

export type AlertItem = {
  id: number;
  user_id: number;
  article_id?: number;
  alert_type: string;
  priority: string;
  channels: string[];
  title: string;
  message: string;
  read_at?: string;
  created_at: string;
};

export type AlertSettings = {
  enabled_channels: string[];
  available_channels: string[];
  email_configured: boolean;
};

/** The nine classification values. Order matches the wireframe's picker. */
export const CLASSIFICATIONS = [
  "potential_safety_signal",
  "potentially_relevant",
  "adverse_event_related",
  "product_quality_related",
  "duplicate",
  "irrelevant",
  "invalid",
  "insufficient_information",
  "requires_human_review",
] as const;
export type Classification = (typeof CLASSIFICATIONS)[number];

/** The fourteen signal tags. Multi-select, distinct from classification. */
export const SIGNAL_TAGS = [
  "potential_signal",
  "confirmed_signal",
  "under_review",
  "adverse_event",
  "serious_adverse_event",
  "product_quality_issue",
  "lack_of_efficacy",
  "drug_interaction",
  "special_situation",
  "duplicate",
  "invalid",
  "not_relevant",
  "submission_required",
  "submission_not_required",
] as const;
export type SignalTag = (typeof SIGNAL_TAGS)[number];

export type Priority = "p1" | "p2" | "p3";
export type SubmissionStatus =
  | "pending_decision"
  | "approved_for_submission"
  | "retained_internally"
  | "submitted";

/** Turn an enum value into the sentence-case label the screens display. */
export function humanise(value?: string | null): string {
  if (!value) return "—";
  const text = value.replace(/_/g, " ");
  return text.charAt(0).toUpperCase() + text.slice(1);
}

export type WorkspaceFolder = {
  key: string;
  label: string;
  count: number;
};

/** Every filter the workspace bar exposes. Dashboard tiles emit this shape. */
export type ArticleFilters = {
  folder?: string;
  queue?: string;
  status?: string;
  product_id?: number;
  active_ingredient_id?: number;
  date_from?: string;
  date_to?: string;
  literature_source_id?: number;
  classification?: string;
  classification_group?: "relevant";
  screened_only?: boolean;
  status_group?: "awaiting_review";
  priority?: string;
  submission_status?: string;
  review_status?: "open" | "closed" | "all";
  signal_status?: string;
  assignee_id?: number;
  assignee_name?: string | null;
  mine_only?: boolean;
  overdue_only?: boolean;
  open_only?: boolean;
  include_archive?: boolean;
  q?: string;
};

export type LiteratureSource = {
  id: number;
  name: string;
  kind: string;
  provider?: string | null;
  access_model: string;
  retrieval?: string | null;
  coverage?: string | null;
  is_enabled: boolean;
  article_count: number;
};

export type SourceConnection = {
  source_name: string;
  contact_email?: string | null;
  contact_email_configured: boolean;
  api_key_configured: boolean;
  api_key_hint?: string | null;
  rate_limit_per_second: number;
  retry_policy: string;
  last_successful_call?: string | null;
  failures_last_7d: number;
  is_healthy: boolean;
};

/** A Step-12 measure, carrying the exact filter the workspace should apply. */
export type DashboardMetric = {
  key: string;
  label: string;
  count: number;
  filter: ArticleFilters;
};

export type DashboardMetrics = {
  scope: string;
  metrics: DashboardMetric[];
  alerts_by_priority: DashboardMetric[];
  results_by_product: {
    product_id: number;
    product_name: string;
    count: number;
    filter: ArticleFilters;
  }[];
  results_by_ingredient: {
    active_ingredient_id: number;
    active_ingredient_name: string;
    count: number;
    filter: ArticleFilters;
  }[];
  results_by_source: {
    literature_source_id: number;
    literature_source_name: string;
    count: number;
    filter: ArticleFilters;
  }[];
  search_completion_status: {
    product_id: number;
    product_name: string;
    status: string;
    origin: "manual" | "scheduled" | null;
    last_run_at: string | null;
    filter: ArticleFilters;
  }[];
};

export type ExceptionSummary = {
  total: number;
  notice: string;
  causes: { cause: string; label: string; count: number; alerted: boolean }[];
};

export type RegulatoryValidation = {
  article_id: number;
  rules_configured: boolean;
  prototype_notice: string;
  fields: {
    field: string;
    label: string;
    required: boolean;
    value: unknown;
    state: "present" | "missing" | "not_stated";
  }[];
  blocking_errors: string[];
  can_generate: boolean;
};

export type RegulatoryRecord = {
  id: number;
  article_id: number;
  latest_export_id?: number | null;
  decision: SubmissionStatus;
  decision_reason?: string | null;
  gateway?: string | null;
  submission_reference?: string | null;
  acknowledgement?: string | null;
  submitted_at?: string | null;
  created_at: string;
  updated_at: string;
};

export type ExportPackage = {
  id: number;
  filename: string;
  record_count: number;
  article_ids: number[];
  payload_json: Record<string, unknown>;
  created_at: string;
};

/** One paper retrieved for an assistant answer. `article_id` is present when
 *  the paper is already a monitored article. `cited` distinguishes papers the
 *  answer actually drew on from ones merely retrieved. */
export type AssistantSource = {
  number: number;
  pmid: string;
  title: string;
  journal?: string | null;
  pub_date?: string | null;
  url: string;
  article_id?: number | null;
  cited: boolean;
};

/** A span of answer text with the citations the API attached to it. Citations
 *  come from the model's citation mechanism, not from prose it wrote, so each
 *  one names a source and quotes the sentence it came from. */
export type AssistantSegment = {
  text: string;
  citations: number[];
  quotes: string[];
};

export type AssistantAnswer = {
  question: string;
  /** The self-contained form — differs when the question was a follow-up. */
  interpreted_question: string;
  answer: string;
  segments: AssistantSegment[];
  sources: AssistantSource[];
  pubmed_query: string;
  total_matches: number;
  model_id: string;
  /** False when the answer is retrieved abstracts rather than synthesis. */
  synthesised: boolean;
  notice: string;
  warning?: string | null;
};

export type AssistantTurn = { question: string; answer: string };

export type AuditEvent = {
  id: number;
  actor: string;
  action: string;
  entity_type: string;
  entity_id?: string | null;
  payload: Record<string, unknown>;
  created_at: string;
};

export type AuditFacets = {
  actors: string[];
  actions: string[];
  entity_types: string[];
};

export type DashboardSummary = {
  scope: string;
  total_articles: number;
  awaiting_review: number;
  unassigned: number;
  potential_signals: number;
  confirmed_signals: number;
  valid_icsr: number;
  not_relevant: number;
  deferred: number;
  overdue: number;
  unread_alerts: number;
  by_product: { product_id: number; product_name: string; count: number }[];
  by_queue: { queue: string; count: number }[];
  score_buckets: { band: string; count: number }[];
  intake_trend: { date: string; count: number }[];
};

export type QueueStats = {
  expedited: number;
  priority: number;
  standard: number;
  qc_sample: number;
  auto_clear: number;
  valid_icsr: number;
  not_case: number;
  deferred: number;
  second_review: number;
};

export type ArticleListItem = {
  id: number;
  pmid: string;
  title: string;
  journal?: string;
  pub_date?: string;
  status: string;
  product_id: number;
  product_name?: string;
  active_ingredients: ActiveIngredient[];
  composite?: number;
  queue?: string;
  sla_due_at?: string;
  hard_rule_triggered: boolean;
  assignee_id?: number;
  assignee_name?: string;
  signal_status: string;
  priority: Priority;
  ai_classification?: Classification | null;
  human_classification?: Classification | null;
  /** Human verdict where one exists, otherwise the AI's proposal. */
  effective_classification?: Classification | null;
  signal_tags: string[];
  literature_source_id?: number | null;
  literature_source_name?: string | null;
};

export type ArticleDetail = {
  id: number;
  pmid: string;
  doi?: string;
  title: string;
  abstract?: string;
  journal?: string;
  authors: string[];
  pub_date?: string;
  mesh_terms: string[];
  publication_types: string[];
  pubmed_url?: string;
  status: string;
  product_id: number;
  product_name?: string;
  active_ingredients: ActiveIngredient[];
  assignee_id?: number;
  assignee_name?: string | null;
  signal_status: string;
  priority: Priority;
  ai_classification?: Classification | null;
  human_classification?: Classification | null;
  signal_tags: string[];
  literature_source_id?: number | null;
  literature_source_name?: string | null;
  search_date?: string | null;
  search_terms?: string | null;
  submission_status: SubmissionStatus;
  latest_screening?: {
    product_match: number;
    event_relevance: number;
    icsr_criteria_match: number;
    composite: number;
    entities: Record<string, unknown>;
    /** Step-5 extraction, promoted out of the loose entities blob. */
    indication?: string | null;
    dosage?: string | null;
    outcome?: string | null;
    seriousness?: string | null;
    country_of_occurrence?: string | null;
    reporter_type?: string | null;
    concomitant_medication?: string | null;
    article_excerpts: string[];
    relevance_reason?: string | null;
    confidence?: number | null;
    processed_at?: string | null;
    icsr_precheck: Record<string, unknown>;
    reason_tags: { code: string; label: string; confidence: number }[];
    hard_rule_candidates: string[];
    summary_for_reviewer?: string;
    model_id: string;
    prompt_version: string;
    ruleset_version: string;
    threshold_version: string;
    is_mock: boolean;
    created_at: string;
  };
  active_triage?: {
    queue: string;
    sla_hours: number;
    sla_due_at: string;
    hard_rule_triggered: boolean;
    hard_rules: string[];
  };
  decisions: Record<string, unknown>[];
  audit_events?: Record<string, unknown>[];
};

export type EvalResult = {
  n: number;
  tp: number;
  fp: number;
  tn: number;
  fn: number;
  sensitivity: number | null;
  specificity: number | null;
  precision: number | null;
  f1: number | null;
  missed_cases: Record<string, unknown>[];
  details: Record<string, unknown>[];
};

export type SearchRunDetail = {
  id: number;
  search_string_id: number;
  status: string;
  query_snapshot: string;
  date_from?: string;
  date_to?: string;
  hit_count: number;
  new_article_count: number;
  rehit_count: number;
  error_message?: string;
  triggered_by?: string;
  started_at?: string;
  completed_at?: string;
  created_at: string;
  product_id?: number;
  product_name?: string;
  articles: {
    id: number;
    pmid: string;
    title: string;
    status: string;
    is_first_seen: boolean;
    composite?: number;
    queue?: string;
  }[];
};

export type ThresholdsConfig = {
  prompt_version: string;
  ruleset_version: string;
  threshold_version: string;
  bands: Record<string, unknown>[];
  auto_clear_qc_sample_rate: number;
  llm_mock: boolean;
  llm_model: string;
  llm_base_url?: string;
  llm_api_key_configured?: boolean;
  llm_mode?: string;
  fail_open_on_llm_error?: boolean;
  ncbi_email_configured?: boolean;
  ncbi_api_key_configured?: boolean;
};

function qs(params: Record<string, string | undefined>) {
  const u = new URLSearchParams();
  Object.entries(params).forEach(([k, v]) => {
    if (v != null && v !== "") u.set(k, v);
  });
  const s = u.toString();
  return s ? `?${s}` : "";
}

/** Serialise the workspace filter set.
 *
 *  A folder already pins the workflow state, so `open_only` is dropped when
 *  one is set — otherwise the Archived and Submitted folders would come back
 *  empty. Booleans are only sent when true, since the API defaults suffice.
 */
function articleQs(f?: ArticleFilters): string {
  if (!f) return "";
  const num = (v?: number) => (v == null ? undefined : String(v));
  return qs({
    folder: f.folder,
    queue: f.queue,
    status: f.status,
    product_id: num(f.product_id),
    active_ingredient_id: num(f.active_ingredient_id),
    date_from: f.date_from,
    date_to: f.date_to,
    literature_source_id: num(f.literature_source_id),
    classification: f.classification,
    classification_group: f.classification_group,
    screened_only: f.screened_only ? "true" : undefined,
    status_group: f.status_group,
    priority: f.priority,
    submission_status: f.submission_status,
    review_status: f.review_status,
    signal_status: f.signal_status,
    assignee_id: num(f.assignee_id),
    q: f.q,
    mine_only: f.mine_only ? "true" : undefined,
    overdue_only: f.overdue_only ? "true" : undefined,
    include_archive: f.include_archive ? "true" : undefined,
    open_only: f.folder ? undefined : f.open_only === false ? "false" : undefined,
  });
}

export const api = {
  async login(email: string, password: string) {
    const body = new URLSearchParams();
    body.set("username", email);
    body.set("password", password);
    const res = await fetch(`${API_BASE}/api/auth/login`, {
      method: "POST",
      headers: { "Content-Type": "application/x-www-form-urlencoded" },
      body,
    });
    if (!res.ok) throw new Error("Login failed");
    return res.json() as Promise<{ access_token: string }>;
  },
  me: () => request<User>("/api/auth/me"),
  users: () => request<User[]>("/api/users"),
  presence: () => request<Presence>("/api/presence"),
  updatePresence: (status: Presence["status"]) =>
    request<Presence>("/api/presence", {
      method: "PATCH",
      body: JSON.stringify({ status }),
    }),
  queueStats: (mineOnly = false) =>
    request<QueueStats>(`/api/queues/stats${mineOnly ? "?mine_only=true" : ""}`),
  articles: (opts?: ArticleFilters) =>
    request<ArticleListItem[]>(`/api/articles${articleQs(opts)}`),
  /** The nine workflow folders with counts under the current filters. */
  workspaceFolders: (opts?: ArticleFilters) =>
    request<{ scope: string; folders: WorkspaceFolder[] }>(
      `/api/workspace/folders${articleQs(opts)}`
    ),
  article: (id: number) => request<ArticleDetail>(`/api/articles/${id}`),
  claim: (id: number) =>
    request(`/api/articles/${id}/claim`, { method: "POST" }),
  review: (id: number, payload: Record<string, unknown>) =>
    request(`/api/articles/${id}/review`, {
      method: "POST",
      body: JSON.stringify(payload),
    }),
  rescore: (id: number) =>
    request(`/api/articles/${id}/rescore`, { method: "POST" }),
  recall: (id: number, rationale?: string) =>
    request(`/api/articles/${id}/recall`, {
      method: "POST",
      body: JSON.stringify({ rationale }),
    }),
  products: () => request<Product[]>("/api/products"),
  updateProduct: (
    id: number,
    body: Partial<Product> & { active_ingredient_ids?: number[] },
  ) =>
    request<Product>(`/api/products/${id}`, {
      method: "PATCH",
      body: JSON.stringify(body),
    }),
  searchStrings: () =>
    request<
      {
        id: number;
        product_id: number;
        query_text: string;
        version: number;
        is_active: boolean;
        notes?: string;
      }[]
    >("/api/search-strings"),
  createSearchString: (body: {
    product_id: number;
    query_text: string;
    notes?: string;
  }) =>
    request<{
      id: number;
      product_id: number;
      query_text: string;
      version: number;
      is_active: boolean;
    }>("/api/search-strings", {
      method: "POST",
      body: JSON.stringify(body),
    }),
  searchRuns: () => request<Record<string, unknown>[]>("/api/search-runs"),
  searchRun: (id: number) =>
    request<SearchRunDetail>(`/api/search-runs/${id}`),
  runSearch: (
    search_string_id: number,
    opts?: { max_fetch?: number; days?: number; date_from?: string; date_to?: string }
  ) =>
    request<Record<string, unknown>>("/api/search-runs", {
      method: "POST",
      body: JSON.stringify({
        search_string_id,
        max_fetch: opts?.max_fetch ?? 20,
        days: opts?.days,
        date_from: opts?.date_from,
        date_to: opts?.date_to,
      }),
    }),
  retrySearchRun: (id: number, max_fetch = 30) =>
    request<SearchRunDetail>(`/api/search-runs/${id}/retry`, {
      method: "POST",
      body: JSON.stringify({ max_fetch }),
    }),
  importPmids: (product_id: number, pmids_text: string) =>
    request("/api/imports/pmids", {
      method: "POST",
      body: JSON.stringify({ product_id, pmids_text }),
    }),
  importCsv: (product_id: number, csv_text: string, fetch_missing = false) =>
    request("/api/imports/csv", {
      method: "POST",
      body: JSON.stringify({
        product_id,
        csv_text,
        fetch_missing_from_pubmed: fetch_missing,
      }),
    }),
  // ── Drug catalogue (NLM RxNorm mirror) ──
  /** Drugs for the picker. With no query this returns the opening page. */
  listDrugs: (q = "", limit?: number) =>
    request<DrugConcept[]>(
      `/api/drugs${qs({ q: q || undefined, limit: limit ? String(limit) : undefined })}`
    ),
  searchDrugs: (q: string, limit?: number) =>
    request<DrugConcept[]>(
      `/api/drugs/search${qs({ q, limit: limit ? String(limit) : undefined })}`
    ),
  drugCatalogStatus: () =>
    request<DrugCatalogStatus>("/api/drugs/status"),
  syncDrugCatalog: () =>
    request<DrugCatalogStatus>("/api/drugs/sync", { method: "POST" }),

  // ── Products ──
  createProduct: (body: {
    name: string;
    inn?: string;
    rxcui?: string;
    /** RxNorm term type, so the server can derive the active substances. */
    tty?: string;
    brands?: string[];
    synonyms?: string[];
    query_text?: string;
  }) =>
    request<Product>("/api/products", {
      method: "POST",
      body: JSON.stringify(body),
    }),
  deactivateProduct: (id: number) =>
    request<Product>(`/api/products/${id}`, { method: "DELETE" }),

  // ── Manual and scheduled search ──
  runSearchNow: (body: {
    drugs?: DrugRef[];
    product_ids?: number[];
    date_from?: string;
    date_to?: string;
    days?: number;
    max_fetch?: number;
  }) =>
    request<RunNowResult>("/api/search-runs/run-now", {
      method: "POST",
      body: JSON.stringify(body),
    }),
  searchSchedules: () =>
    request<SearchSchedule[]>("/api/search-schedules"),
  createSchedules: (body: {
    drugs?: DrugRef[];
    product_ids?: number[];
    frequency: ScheduleFrequency;
    end_date: string;
    lookback_days?: number;
    max_fetch?: number;
  }) =>
    request<SearchSchedule[]>("/api/search-schedules", {
      method: "POST",
      body: JSON.stringify(body),
    }),
  updateSchedule: (id: number, body: Record<string, unknown>) =>
    request<SearchSchedule>(`/api/search-schedules/${id}`, {
      method: "PATCH",
      body: JSON.stringify(body),
    }),
  deleteSchedule: (id: number) =>
    request<SearchSchedule>(`/api/search-schedules/${id}`, { method: "DELETE" }),
  runDueSchedules: () =>
    request<{ fired: number; results: Record<string, unknown>[] }>(
      "/api/search-schedules/run-due",
      { method: "POST" }
    ),

  exportIcsr: () =>
    request<Record<string, unknown>>("/api/exports/icsr", { method: "POST" }),
  /** CDSCO / NCC-PvPI E2B(R2) ichicsr XML export. */
  exportCdscoXml: () =>
    request<Record<string, unknown>>("/api/exports/cdsco-xml", { method: "POST" }),
  downloadCdscoXmlUrl: (id: number) => `${API_BASE}/api/exports/${id}/xml`,
  activeIngredients: () =>
    request<ActiveIngredient[]>("/api/active-ingredients"),
  createActiveIngredient: (body: {
    name: string;
    inn?: string;
    atc_code?: string;
  }) =>
    request<ActiveIngredient>("/api/active-ingredients", {
      method: "POST",
      body: JSON.stringify(body),
    }),
  setProductIngredients: (product_id: number, active_ingredient_ids: number[]) =>
    request<Product>(`/api/products/${product_id}`, {
      method: "PATCH",
      body: JSON.stringify({ active_ingredient_ids }),
    }),
  exportParallel: (product_id?: number) =>
    request<Record<string, unknown>>(
      `/api/exports/parallel-run${product_id ? `?product_id=${product_id}` : ""}`,
      { method: "POST" }
    ),
  exports: () => request<Record<string, unknown>[]>("/api/exports"),
  downloadExportUrl: (id: number, format: "json" | "csv" = "json") =>
    `${API_BASE}/api/exports/${id}?format=${format}`,
  evaluation: () =>
    request<EvalResult>("/api/evaluation/run", { method: "POST" }),
  thresholds: () => request<ThresholdsConfig>("/api/config/thresholds"),
  dashboard: (mineOnly = false) =>
    request<DashboardSummary>(
      `/api/dashboard/summary${mineOnly ? "?mine_only=true" : ""}`
    ),
  dashboardMetrics: (mineOnly = false) =>
    request<DashboardMetrics>(
      `/api/dashboard/metrics${mineOnly ? "?mine_only=true" : ""}`
    ),
  alerts: (opts?: {
    unread_only?: boolean;
    priority?: string;
    product_id?: number;
    alert_type?: string;
    created_from?: string;
    created_to?: string;
  }) =>
    request<AlertItem[]>(
      `/api/alerts${qs({
        unread_only: opts?.unread_only ? "true" : undefined,
        priority: opts?.priority,
        product_id: opts?.product_id ? String(opts.product_id) : undefined,
        alert_type: opts?.alert_type,
        created_from: opts?.created_from,
        created_to: opts?.created_to,
      })}`
    ),
  alertSettings: () => request<AlertSettings>("/api/alerts/settings"),
  readAlert: (id: number) =>
    request<AlertItem>(`/api/alerts/${id}/read`, { method: "POST" }),
  readAllAlerts: () =>
    request<{ updated: number }>("/api/alerts/read-all", { method: "POST" }),

  // ── Classification and signal tags ──
  /** Record the human verdict. The AI's proposal is retained separately. */
  setClassification: (id: number, classification: Classification, rationale?: string) =>
    request<{
      article_id: number;
      ai_classification: string | null;
      human_classification: string;
    }>(`/api/articles/${id}/classification`, {
      method: "PATCH",
      body: JSON.stringify({ classification, rationale }),
    }),
  /** Replace the whole tag set — the panel is a multi-select, not a toggle. */
  setSignalTags: (id: number, tags: string[]) =>
    request<{ article_id: number; signal_tags: string[]; signal_status: string }>(
      `/api/articles/${id}/signal-tags`,
      { method: "PUT", body: JSON.stringify({ tags }) }
    ),

  // ── Literature sources ──
  literatureSources: () => request<LiteratureSource[]>("/api/literature-sources"),
  createLiteratureSource: (body: Partial<LiteratureSource> & { name: string }) =>
    request<LiteratureSource>("/api/literature-sources", {
      method: "POST",
      body: JSON.stringify(body),
    }),
  updateLiteratureSource: (id: number, body: Partial<LiteratureSource>) =>
    request<LiteratureSource>(`/api/literature-sources/${id}`, {
      method: "PATCH",
      body: JSON.stringify(body),
    }),
  sourceConnection: () =>
    request<SourceConnection>("/api/literature-sources/connection"),

  // ── Regulatory (prototype — the app never transmits) ──
  regulatoryValidate: (articleId: number) =>
    request<RegulatoryValidation>(
      `/api/regulatory/articles/${articleId}/validate`
    ),
  regulatoryGenerate: (
    articleId: number,
    body?: { sender_id?: string; receiver_id?: string }
  ) =>
    request<Record<string, unknown>>(
      `/api/regulatory/articles/${articleId}/generate`,
      { method: "POST", body: JSON.stringify(body ?? {}) }
    ),
  regulatoryVersions: (articleId: number) =>
    request<ExportPackage[]>(
      `/api/regulatory/articles/${articleId}/versions`
    ),
  async downloadRegulatoryXml(exportId: number, filename?: string) {
    const headers: HeadersInit = {};
    if (token) headers.Authorization = `Bearer ${token}`;
    const res = await fetch(`${API_BASE}/api/exports/${exportId}/xml`, { headers });
    if (!res.ok) throw new Error(formatApiError(await res.text(), res.statusText));
    const blob = await res.blob();
    const url = URL.createObjectURL(blob);
    const anchor = document.createElement("a");
    anchor.href = url;
    anchor.download = filename || `regulatory_${exportId}.xml`;
    anchor.click();
    URL.revokeObjectURL(url);
  },
  regulatoryRecord: (articleId: number) =>
    request<RegulatoryRecord | null>(
      `/api/regulatory/articles/${articleId}/record`
    ),
  regulatoryDecision: (
    articleId: number,
    body: { decision: SubmissionStatus; reason: string }
  ) =>
    request<RegulatoryRecord>(
      `/api/regulatory/articles/${articleId}/decision`,
      { method: "POST", body: JSON.stringify(body) }
    ),
  regulatorySubmission: (
    articleId: number,
    body: {
      gateway: string;
      submission_reference: string;
      submitted_at?: string;
      acknowledgement?: string;
    }
  ) =>
    request<RegulatoryRecord>(
      `/api/regulatory/articles/${articleId}/submission`,
      { method: "POST", body: JSON.stringify(body) }
    ),

  exceptionSummary: (opts?: { product_id?: number; mine_only?: boolean }) =>
    request<ExceptionSummary>(
      `/api/exceptions/summary${qs({
        product_id: opts?.product_id ? String(opts.product_id) : undefined,
        mine_only: opts?.mine_only ? "true" : undefined,
      })}`
    ),

  audit: (opts?: {
    actor?: string;
    entity_type?: string;
    entity_id?: string;
    action?: string;
    created_from?: string;
    created_to?: string;
  }) =>
    request<AuditEvent[]>(
      `/api/audit${qs({
        actor: opts?.actor,
        entity_type: opts?.entity_type,
        entity_id: opts?.entity_id,
        action: opts?.action,
        created_from: opts?.created_from,
        created_to: opts?.created_to,
      })}`
    ),
  auditFacets: () => request<AuditFacets>("/api/audit/facets"),
  async downloadAudit(opts?: {
    actor?: string;
    entity_type?: string;
    action?: string;
    created_from?: string;
    created_to?: string;
  }) {
    const headers: HeadersInit = {};
    if (token) headers.Authorization = `Bearer ${token}`;
    const res = await fetch(
      `${API_BASE}/api/audit/export${qs({
        actor: opts?.actor,
        entity_type: opts?.entity_type,
        action: opts?.action,
        created_from: opts?.created_from,
        created_to: opts?.created_to,
      })}`,
      { headers }
    );
    if (!res.ok) throw new Error(formatApiError(await res.text(), res.statusText));
    const blob = await res.blob();
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = `litmon_audit_${new Date().toISOString().slice(0, 10)}.csv`;
    a.click();
    URL.revokeObjectURL(url);
  },
  slaOverdue: () =>
    request<{ count: number; items: Record<string, unknown>[] }>("/api/sla/overdue"),
  slaSummary: () => request<Record<string, unknown>>("/api/sla/summary"),
  slaNotify: () =>
    request<{ job_id: number; status: string }>("/api/sla/notify", {
      method: "POST",
    }),
  opsMetrics: () => request<Record<string, unknown>>("/api/ops/metrics"),
  publicMetrics: () => request<Record<string, unknown>>("/api/metrics"),
  jobs: (status?: string) =>
    request<Record<string, unknown>[]>(
      `/api/jobs${status ? `?status=${status}` : ""}`
    ),
  assistantAsk: (
    question: string,
    opts?: { limit?: number; history?: AssistantTurn[] },
  ) =>
    request<AssistantAnswer>("/api/assistant/ask", {
      method: "POST",
      body: JSON.stringify({
        question,
        ...(opts?.limit ? { limit: opts.limit } : {}),
        ...(opts?.history?.length ? { history: opts.history } : {}),
      }),
    }),
  batchRescore: (body: { article_ids?: number[]; all_open?: boolean }) =>
    request<Record<string, unknown>>("/api/jobs/batch-rescore", {
      method: "POST",
      body: JSON.stringify(body),
    }),
  retryJob: (id: number) =>
    request<Record<string, unknown>>(`/api/jobs/${id}/retry`, { method: "POST" }),
  async downloadExport(id: number, format: "json" | "csv" = "csv") {
    const headers: HeadersInit = {};
    if (token) headers.Authorization = `Bearer ${token}`;
    const res = await fetch(
      `${API_BASE}/api/exports/${id}?format=${format}`,
      { headers }
    );
    if (!res.ok) throw new Error(await res.text());
    const blob = await res.blob();
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = `export_${id}.${format}`;
    a.click();
    URL.revokeObjectURL(url);
  },
};
