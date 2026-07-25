const API_BASE = import.meta.env.VITE_API_BASE || "";

let token: string | null = localStorage.getItem("litmon_token");

export function setToken(t: string | null) {
  token = t;
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
    throw new Error(text || res.statusText);
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
  composite?: number;
  queue?: string;
  sla_due_at?: string;
  hard_rule_triggered: boolean;
  assignee_id?: number;
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
  assignee_id?: number;
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
  queueStats: () => request<QueueStats>("/api/queues/stats"),
  articles: (opts?: {
    queue?: string;
    open_only?: boolean;
    include_archive?: boolean;
    q?: string;
    status?: string;
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
  products: () =>
    request<{ id: number; name: string; synonyms: string[] }[]>("/api/products"),
  searchStrings: () =>
    request<
      { id: number; product_id: number; query_text: string; version: number }[]
    >("/api/search-strings"),
  searchRuns: () => request<Record<string, unknown>[]>("/api/search-runs"),
  runSearch: (search_string_id: number, max_fetch = 20) =>
    request("/api/search-runs", {
      method: "POST",
      body: JSON.stringify({ search_string_id, max_fetch }),
    }),
  seedDemo: () =>
    request<{ seeded: number }>("/api/demo/seed-articles", { method: "POST" }),
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
  exportIcsr: () =>
    request<Record<string, unknown>>("/api/exports/icsr", { method: "POST" }),
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
  thresholds: () => request<Record<string, unknown>>("/api/config/thresholds"),
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
