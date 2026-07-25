# Changelog

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
