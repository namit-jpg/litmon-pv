# REST API reference (pilot)

Base URL (local): `http://127.0.0.1:8000`
Interactive docs: `/docs` (Swagger) · `/redoc`

Most routes require:

```http
Authorization: Bearer <access_token>
```

Obtain token via `POST /api/auth/login` (OAuth2 password form: `username` = email, `password`).

---

## Auth

| Method | Path | Auth | Description |
|--------|------|------|-------------|
| POST | `/api/auth/login` | No | Login; returns `{ access_token }` |
| GET | `/api/auth/me` | Yes | Current user |
| GET | `/api/users` | Yes | Active users for pilot assignment |

Rate limit: 10 login attempts / 5 minutes per IP+email.

---

## Products & search

| Method | Path | Roles | Description |
|--------|------|-------|-------------|
| GET | `/api/products` | any | List monitored products |
| POST | `/api/products` | pv_lead, admin | Create a monitored product and its PV ownership details |
| PATCH | `/api/products/{id}` | pv_lead, admin | Update product config and primary reviewer; reassigns open work |
| GET | `/api/search-strings` | any | Versioned PubMed queries |
| POST | `/api/search-strings` | pv_lead, admin | Create new active search string |
| GET | `/api/search-runs` | any | Recent PubMed search runs |
| GET | `/api/search-runs/{id}` | any | Search-run detail + article appearances |
| POST | `/api/search-runs` | reviewer+ | Live ESearch→EFetch→score (`days` 7/14/30 or `date_from`/`date_to`) |
| POST | `/api/search-runs/{id}/retry` | reviewer+ | Re-run same string + date window (new SearchRun row) |

### Literature sources and recurring searches

| Method | Path | Roles | Description |
|--------|------|-------|-------------|
| GET, POST | `/api/literature-sources` | GET any; POST pv_lead, admin | List or create literature-source records |
| PATCH | `/api/literature-sources/{id}` | pv_lead, admin | Update source metadata or enablement; a source cannot be enabled without a retrieval path |
| GET | `/api/literature-sources/connection` | any | Persisted PubMed connection/run health for the last seven days |
| GET, POST | `/api/search-schedules` | GET any; POST reviewer+ | List or create per-product recurring searches |
| PATCH, DELETE | `/api/search-schedules/{id}` | reviewer+ | Update/resume or stop a schedule; stop is soft and remains audited |
| POST | `/api/search-schedules/run-due` | pv_lead, admin | Run currently due schedules now; useful for pilot testing or an external scheduler |
| GET | `/api/exceptions/summary` | any | Itemised exception-queue counts without collapsing the unresolved `invalid` meanings |

---

## Import

| Method | Path | Description |
|--------|------|-------------|
| POST | `/api/imports/pmids` | Body: `{ product_id, pmids_text }` — EFetch + score |
| POST | `/api/imports/csv` | Body: `{ product_id, csv_text, fetch_missing_from_pubmed }` |

CSV columns: `pmid` (required), `title`, `abstract`, `journal`, `doi`, `pub_date`.

---

## Articles & review

| Method | Path | Description |
|--------|------|-------------|
| GET | `/api/articles` | Workspace query: `queue`, `status`, `product_id`, `active_ingredient_id`, `date_from`, `date_to`, `literature_source_id`, `classification`, `signal_status`, `submission_status`, `assignee_id`, `priority`, `review_status`, `mine_only`, `open_only`, `include_archive`, `overdue_only`, `q` |
| GET | `/api/articles/{id}` | Detail + screening + triage + decisions + audit |
| POST | `/api/articles/{id}/claim` | Assign to current user |
| POST | `/api/articles/{id}/review` | Decision (see actions below) |
| POST | `/api/articles/{id}/rescore` | Re-run AI + triage |
| POST | `/api/articles/{id}/recall` | Bring from archive to review |

### Review actions (`action` field)

- `confirm_not_case`
- `confirm_valid_icsr`
- `override_ai`
- `request_second_review`
- `defer_full_text`
- `recall_to_review`
- `mark_potential_signal`
- `confirm_signal` (PV lead or admin, and only after a review decision exists)
- `reject_signal`
- `mark_invalid`
- `mark_duplicate`
- `mark_not_relevant`
- `prepare_for_submission`
- `retain_internally`
- `close_report`

Include explicit ICSR checklist booleans when confirming cases.

---

## Queues & SLA

| Method | Path | Description |
|--------|------|-------------|
| GET | `/api/queues/stats` | Counts per queue/status plus `classification_counts` keyed by the nine-class taxonomy |
| GET | `/api/sla/overdue` | Past-SLA open articles |
| GET | `/api/sla/summary` | Overdue rollup |
| POST | `/api/sla/notify` | Enqueue SLA check job |

---

## Pilot dashboard and alerts

| Method | Path | Description |
|--------|------|-------------|
| GET | `/api/dashboard/summary?mine_only=true` | Assignment, unassigned triage, signal, ICSR, overdue, and product counts |
| GET | `/api/dashboard/metrics?mine_only=true` | Step-12 measures, each with a workspace drill-through filter payload |
| GET | `/api/workspace/folders` | Current user's workflow-folder counts and filters |
| GET | `/api/alerts` | Current user's persistent alerts; supports `unread_only`, `priority`, `product_id`, `alert_type`, `created_from`, `created_to` |
| GET | `/api/alerts/settings` | Pilot alert delivery settings: persistent in-app inbox only |
| POST | `/api/alerts/{id}/read` | Mark one alert read |
| POST | `/api/alerts/read-all` | Mark all current-user alerts read |
| GET | `/api/presence` | Current reviewer presence, active work, and capacity |
| PATCH | `/api/presence` | Set current reviewer to `available`, `busy`, or `offline` |

---

## Regulatory output, submission and export

The regulatory workflow is a prototype. It never transmits to a gateway. A
PV user generates a validated package, downloads it, uploads it manually, and
records the resulting reference.

| Method | Path | Description |
|--------|------|-------------|
| GET | `/api/regulatory/articles/{id}/validate` | Resolve the deployment-configured mandatory-field registry and report blocking omissions |
| POST | `/api/regulatory/articles/{id}/generate` | Generate a versioned one-article E2B(R2)-shaped XML package; returns 422 while validation is blocked |
| GET | `/api/regulatory/articles/{id}/versions` | List the article's generated regulatory package versions |
| GET | `/api/regulatory/articles/{id}/record` | Read the recorded decision and manual gateway evidence; returns `null` before the first decision |
| POST | `/api/regulatory/articles/{id}/decision` | Record `approved_for_submission` or `retained_internally` with a reason |
| POST | `/api/regulatory/articles/{id}/submission` | Record manual gateway, reference, timestamp and acknowledgement; only after an approved decision and generated package |

The field registry is supplied through `REGULATORY_MANDATORY_FIELDS_JSON`.
`.env.example` carries a minimal prototype registry for PMID, suspect product,
and adverse event so the versioning workflow can be exercised. Deployments must
replace it when the partner supplies the official specification. Every output
continues to say that it is a prototype and not a validated CDSCO submission.

| Method | Path | Description |
|--------|------|-------------|
| POST | `/api/exports/icsr` | Package confirmed ICSRs |
| POST | `/api/exports/parallel-run` | Comparison sheet for manual process |
| GET | `/api/exports` | List packages |
| GET | `/api/exports/{id}?format=json\|csv` | Download |

---

## Evaluation & config

| Method | Path | Description |
|--------|------|-------------|
| POST | `/api/evaluation/run` | Gold-label sensitivity/specificity |
| GET | `/api/config/thresholds` | Bands, versions, QC rate, LLM mock/live mode, NCBI config flags |

---

## Jobs & ops

| Method | Path | Description |
|--------|------|-------------|
| GET | `/api/jobs` | Background jobs |
| GET | `/api/jobs/{id}` | Job detail |
| POST | `/api/jobs/batch-rescore` | `{ article_ids }` or `{ all_open: true }` |
| POST | `/api/jobs/run-search` | Async PubMed search |
| POST | `/api/jobs/{id}/retry` | Retry failed job |
| GET | `/api/ops/metrics` | Auth metrics + SLA |
| GET | `/api/metrics` | Lightweight metrics snapshot |
| GET | `/api/audit` | Audit events |

---

## Health

| Method | Path | Description |
|--------|------|-------------|
| GET | `/health` | Liveness |
| GET | `/health/ready` | DB readiness |

---

## Queues (routing)

| Queue | Typical composite / trigger | SLA (pilot clocks) |
|-------|----------------------------|--------------------|
| Auto-Clear | &lt; 0.15 | QC sample 10% |
| Standard | 0.15–0.65 | 5 days |
| Priority | 0.65–0.85 | 2 days |
| Expedited | ≥ 0.85 or hard rule | 24 hours |
| QC sample | Random from auto-clear | 5 days |

Hard rules force Expedited: death+product, pregnancy, pediatric, IME, ambiguous ICSR.
