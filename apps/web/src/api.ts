const API_BASE = import.meta.env.VITE_API_BASE || "";

let token: string | null = localStorage.getItem("litmon_token");

export function setToken(t: string | null) {
  token = t;
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
  inn?: string;
  brands: string[];
  synonyms: string[];
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
  title: string;
  message: string;
  read_at?: string;
  created_at: string;
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
  signal_status: string;
  latest_screening?: {
    product_match: number;
    event_relevance: number;
    icsr_criteria_match: number;
    composite: number;
    entities: Record<string, unknown>;
    icsr_precheck: Record<string, unknown>;
    reason_tags: { code: string; label: string; confidence: number }[];
    hard_rule_candidates: string[];
    summary_for_reviewer?: string;
    model_id: string;
    prompt_version: string;
    is_mock: boolean;
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
  articles: (opts?: {
    queue?: string;
    open_only?: boolean;
    include_archive?: boolean;
    q?: string;
    status?: string;
    product_id?: number;
    mine_only?: boolean;
    assignee_id?: number;
    signal_status?: string;
    overdue_only?: boolean;
  }) => {
    const open =
      opts?.include_archive
        ? "false"
        : opts?.open_only === false
          ? "false"
          : "true";
    return request<ArticleListItem[]>(
      `/api/articles${qs({
        queue: opts?.queue,
        open_only: open,
        include_archive: opts?.include_archive ? "true" : undefined,
        q: opts?.q,
        status: opts?.status,
        product_id: opts?.product_id ? String(opts.product_id) : undefined,
        mine_only: opts?.mine_only ? "true" : undefined,
        assignee_id: opts?.assignee_id ? String(opts.assignee_id) : undefined,
        signal_status: opts?.signal_status,
        overdue_only: opts?.overdue_only ? "true" : undefined,
      })}`
    );
  },
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
  updateProduct: (id: number, body: Partial<Product>) =>
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
    product_ids: number[];
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
    product_ids: number[];
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
  alerts: (unreadOnly = false) =>
    request<AlertItem[]>(`/api/alerts${unreadOnly ? "?unread_only=true" : ""}`),
  readAlert: (id: number) =>
    request<AlertItem>(`/api/alerts/${id}/read`, { method: "POST" }),
  readAllAlerts: () =>
    request<{ updated: number }>("/api/alerts/read-all", { method: "POST" }),
  audit: (opts?: { entity_type?: string; entity_id?: string; action?: string }) =>
    request<Record<string, unknown>[]>(
      `/api/audit${qs({
        entity_type: opts?.entity_type,
        entity_id: opts?.entity_id,
        action: opts?.action,
      })}`
    ),
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
