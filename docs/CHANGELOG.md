# Changelog

## Unreleased — Product Search, drug catalogue, scheduled searches

- **Products can now be created in the app.** There was no `POST /api/products`
  at all previously — products only existed if `bootstrap.py` wrote them
- New **Product Search** tab: multi-select products, run a manual search over a
  date range, or schedule one to repeat. Reviewers can search and schedule;
  creating or removing a product stays with PV Lead/Admin
- **Drug catalogue mirrored from NLM RxNorm** (free, no API key, same body as
  PubMed). 23.6k ingredient / combination / brand concepts synced locally so the
  picker is instant and survives a network drop. Typeahead returns at most 100
  matches, ranked exact → prefix → term type → shortest name
- Creating a product auto-generates a versioned starter PubMed query from its
  names plus standard safety terms, editable afterwards
- **Recurring searches**: daily / weekly / monthly with a bounded end date.
  `next_run_at` is persisted rather than held in a timer, so schedules survive a
  restart; after downtime a schedule resumes once instead of firing a backlog.
  Monthly advance is calendar-aware (31 Jan → 28/29 Feb). A new schedule
  supersedes the previous one for that product so NCBI is never double-hit
- Schedules run via an in-process runner and a `POST /api/search-schedules/run-due`
  endpoint, so external cron can drive them instead
- **Role-gated navigation.** Reviewers see Dashboard, My Work, Product Search and
  Archive; Ops/Audit/Admin are restricted. Routes redirect rather than only
  hiding links, and `GET /api/audit`, `/api/jobs` and `/api/ops/metrics` are now
  PV Lead/Admin — previously any authenticated user could read the audit trail
- Product soft-delete stops its schedules and keeps articles and audit history

### Seeded and demo data removed
- `bootstrap.py` now seeds only user accounts — no products, search strings or
  API tags
- Removed `seed_demo_articles_async`, `POST /api/demo/seed-articles` and the
  Admin "Seed demo articles" button
- Removed the DrugX gold fixture and its hardcoded product names. Evaluation now
  scores against the products actually being monitored and reports
  "not configured" when no validation set is present, rather than publishing a
  sensitivity KPI computed on invented articles
- Removed prefilled demo credentials from the login form, the hardcoded query
  examples and "prefer Ibuprofen" default in Admin, and the demo CSV sample

## Unreleased — Dashboard charts and light theme

- PV dashboard gains five Chart.js visualisations: triage queue mix, literature
  by product, AI composite score spread, review workflow, and publication
  volume by week
- Chart.js is bundled, not CDN-loaded, so the pilot still runs offline
- Publication volume is bucketed weekly on purpose: PubMed frequently omits the
  day component and the parser falls back to the 1st of the month, which made a
  daily series show large artificial spikes
- Dashboard scope now defaults by role — reviewers open on My dashboard,
  admins and PV leads on All work rather than an empty personal queue
- `by_product` excludes retired products so the dashboard reflects live
  monitoring only
- Nature-inspired light theme: warm paper canvas, forest/fern/stream/clay/honey
  palette, serif display type, system font stacks only (no web-font fetch).
  All six pages verified at WCAG AA contrast

## Unreleased — API tagging and CDSCO export

- Active Pharmaceutical Ingredient (API) modelled as a many-to-many tag
  (`active_ingredients` + `product_active_ingredients`) instead of the single
  `Product.inn` column, so combination products carry several substances and
  one substance spans many products
- `GET/POST/PATCH /api/active-ingredients`; product update accepts
  `active_ingredient_ids`; `GET /api/articles?active_ingredient_id=` returns
  every article across all products carrying that substance
- API tags widen the screening match set and are surfaced in Admin
- CDSCO / NCC-PvPI ICSR export in ICH E2B(R2) `ichicsr` XML form
  (`POST /api/exports/cdsco-xml`, `GET /api/exports/{id}/xml`), with API tags
  mapped to `activesubstancename` (G.k.2.3.r)
- Alembic revision `3c8e1a5f7b92` with backfill from the legacy `inn` column
- Fixed seriousness parsing: `non_serious` was read as serious, which would
  have marked a non-serious case as expedited to the regulator

## Unreleased — Thursday pilot turnaround

- Product-level primary reviewer and automatic assignment of reviewable literature
- My Work/All Work queue scopes with product and signal filtering
- Human-controlled potential/confirmed/rejected signal workflow
- Persistent per-user alert inbox with assignment, signal, search-failure, and SLA events
- PV dashboard with drill-through workload, signal, ICSR, overdue, and product counts
- Service Cloud-style pilot routing: reviewer presence, capacity, primary-reviewer preference, least-loaded fallback, and an unassigned triage state
- Alembic backfill for the default pilot reviewer and existing open articles
- Product-scoped PMID uniqueness and deduplication for four-product monitoring
- Targeted assignment/signal/alert tests and repaired frontend TypeScript build

## 0.2.1 — P0 real-data readiness (2026-07)

### PubMed live path
- Friendlier NCBI errors (`PubMedError`) with retryable flag and operator guidance  
- Search date-window presets via `days` (7 / 14 / 30) on `POST /api/search-runs`  
- Search-run detail: `GET /api/search-runs/{id}` + React page with articles  
- Retry failed/completed runs: `POST /api/search-runs/{id}/retry` (Admin + detail UI)  
- Admin: date presets, max-fetch, error banners, NCBI config readiness  

### LLM path polish
- Structured prompt helpers + unit tests (`build_user_payload`, `parse_llm_screening_json`)  
- LLM timeout/retry with metrics: `llm_fallbacks`, `llm_timeouts`, `llm_retries`  
- Fail-open to heuristic documented; audit event `llm_fallback_heuristic`  
- Admin runtime config panel: LLM mock/live, key set, NCBI email/key flags  
- Ops dashboard shows LLM fallback/timeout counters  

### Schema
- Alembic initial migration + startup `run_migrations()` (stamp legacy DBs, fallback create_all)

## 0.2.0 — Phase F hardening (2026-07)

- Background job worker (`batch_rescore`, `run_search`, `sla_check`) with failed-job retry  
- SLA overdue detection, Ops dashboard, notifications stub (log/SMTP)  
- Request logging, metrics, security headers, login rate limiting  
- Pilot runbook, perf smoke script  
- Health ready endpoint  

## 0.1.0 — Phase A–E pilot foundation (2026-07)

- FastAPI + React monorepo scaffold  
- PubMed E-utilities search/ingest  
- AI mock scorer + hard-rule triage  
- Reviewer queues, article card, ICSR checklist  
- CSV/PMID import, archive/recall  
- Gold evaluation harness  
- ICSR + parallel-run export (JSON/CSV)  
- Audit trail, seed users/product  
