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

Rate limit: 10 login attempts / 5 minutes per IP+email.

---

## Products & search

| Method | Path | Roles | Description |
|--------|------|-------|-------------|
| GET | `/api/products` | any | List monitored products |
| PATCH | `/api/products/{id}` | pv_lead, admin | Update product synonyms etc. |
| GET | `/api/search-strings` | any | Versioned PubMed queries |
| POST | `/api/search-strings` | pv_lead, admin | Create new active search string |
| GET | `/api/search-runs` | any | Recent PubMed search runs |
| POST | `/api/search-runs` | reviewer+ | Live ESearch→EFetch→score |
| POST | `/api/demo/seed-articles` | pv_lead, admin | Offline demo articles |

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
| GET | `/api/articles` | Query: `queue`, `status`, `open_only`, `include_archive`, `overdue_only`, `q` |
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

Include explicit ICSR checklist booleans when confirming cases.

---

## Queues & SLA

| Method | Path | Description |
|--------|------|-------------|
| GET | `/api/queues/stats` | Counts per queue/status |
| GET | `/api/sla/overdue` | Past-SLA open articles |
| GET | `/api/sla/summary` | Overdue rollup |
| POST | `/api/sla/notify` | Enqueue SLA check job |

---

## Export

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
| GET | `/api/config/thresholds` | Bands, versions, QC rate |

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
