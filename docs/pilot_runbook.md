# LitMon-PV Pilot Runbook

**Audience:** PV Lead, Reviewers, IT support
**System:** Literature Monitoring Automation for Pharmacovigilance (partner-feedback MVP)
**Status:** Not GxP validated — parallel-run only until CSV complete

---

## 1. Daily / weekly checklist

| When | Action | Owner |
|------|--------|-------|
| Weekly (or match configured cadence) | Confirm scheduled search completed; run a bounded search manually only if needed | PV Lead / scheduler |
| After each search | Check **Alerts**, then the workspace folders by priority | Reviewers |
| Daily | Review due-soon and overdue in-app alerts | PV Lead |
| End of cycle | Export parallel-run sheet; complete manual columns | PV Lead |
| End of cycle | Export confirmed ICSRs (JSON/CSV) for case entry | Case processor |
| As needed | Gold evaluation after threshold changes | PV Lead |

---

## 2. Start the system

### Backend

```powershell
cd C:\Users\HP\litmon-pv\apps\api
.\.venv\Scripts\Activate.ps1
$env:PYTHONPATH = (Get-Location).Path
uvicorn app.main:app --host 127.0.0.1 --port 8000
```

### Frontend

```powershell
cd C:\Users\HP\litmon-pv\apps\web
npm run dev
```

### Health

- Liveness: `GET http://127.0.0.1:8000/health`
- Readiness (DB): `GET http://127.0.0.1:8000/health/ready`
- Metrics: `GET http://127.0.0.1:8000/api/metrics`

### Default accounts

| Email | Password | Role |
|-------|----------|------|
| reviewer@litmon.local | reviewer123 | Reviewer |
| pvlead@litmon.local | pvlead123 | PV Lead |
| admin@litmon.local | admin123 | Admin |

**Change passwords before any shared pilot environment.**

---

## 3. Configure PubMed

In `C:\Users\HP\litmon-pv\.env`:

```env
NCBI_EMAIL=your.name@company.com
NCBI_API_KEY=   # free NCBI key recommended
```

Restart API after changes.

---

## 4. Run a literature cycle

1. Confirm the product's active **search string** under **Search & schedule** (versioned query).
2. Run a bounded PubMed search from **Product search**, or let the configured schedule run:
   ```powershell
   cd C:\Users\HP\litmon-pv\apps\api
   .\.venv\Scripts\Activate.ps1
   $env:PYTHONPATH = (Get-Location).Path
   python ..\..\workers\scheduled_search.py --days 7 --max-fetch 50
   ```
3. If PubMed is down: use **Pilot tools** to import CSV or PMIDs.
4. Review the workspace folders (priority first), then open the **Detection report**.
5. Record classification, signal tags, reviewer decision, and the ICSR checklist as applicable.
6. Use **Submission & storage** to validate and generate a prototype regulatory package, then manually record submit-or-retain evidence.
7. Export the parallel-run comparison for sensitivity review when operating in parallel mode.

---

## 5. SLA management

- Expedited: 24h
- Priority: 2 business days (48h clock in pilot)
- Standard / QC: 5 business days (120h clock)

Due-soon and overdue items appear in the persistent **Alerts** inbox and via
`GET /api/sla/overdue`. The scheduler's time-driven check records those alerts;
outbound email is not part of this pilot.

---

## 6. Failure modes

| Symptom | Action |
|---------|--------|
| Search run `failed` | Check Audit + Search runs table; verify NCBI_EMAIL; retry search |
| Import fails | Use CSV with title/abstract offline (`fetch_missing=false`) |
| Job `failed` | **Pilot tools** → Jobs → Retry (dead-letter recovery) |
| Login 429 | Wait 5 minutes (rate limit after repeated failures) |
| API not ready | Check `/health/ready`; ensure `litmon.db` path writable |
| Low sensitivity on eval | Do **not** raise Auto-Clear threshold; investigate FN titles |

---

## 7. Background jobs

| Type | Purpose |
|------|---------|
| `batch_rescore` | Re-score up to 500 articles |
| `run_search` | Async PubMed search |
| `sla_check` | Due-soon / overdue scan + persistent in-app alerts |
| schedule runner | Runs due product searches and monitoring-gap checks while the API is running |

Failed jobs remain in history with error text; **Retry** creates a new job with the same payload.

---

## 8. Backup & restore (pilot)

### Backup

```powershell
# Stop API first for clean SQLite copy
Copy-Item C:\Users\HP\litmon-pv\apps\api\litmon.db C:\Users\HP\litmon-pv\backups\litmon-$(Get-Date -Format yyyyMMdd-HHmm).db
```

Also export audit periodically: Audit page or `GET /api/audit`.

### Restore

1. Stop API.
2. Replace `litmon.db` with backup.
3. Start API.
4. Confirm `/health/ready` and login.

For PostgreSQL, use `pg_dump` / `pg_restore` when `DATABASE_URL` points to Postgres.

---

## 9. Security notes (pilot)

- JWT secret must be changed from default (`JWT_SECRET`).
- Login rate-limited (10 attempts / 5 min per IP+email).
- Security headers: `X-Content-Type-Options`, `X-Frame-Options`, `Referrer-Policy`.
- Banner: **not GxP validated**.
- No silent delete of articles; archive is recallable.

---

## 10. In-app alerts

This MVP intentionally uses the persistent in-app inbox only. Deadline,
overdue, signal, assignment, exception, search-failure and monitoring-gap
events are stored there and acknowledgement is audited. Outbound email, SMS,
chat, WhatsApp and push delivery are not part of this pilot build.

---

## 11. Performance smoke

```powershell
cd C:\Users\HP\litmon-pv\apps\api
.\.venv\Scripts\Activate.ps1
$env:PYTHONPATH = (Get-Location).Path
python ..\..\workers\perf_smoke.py --n 500
```

Target: score/route 500 synthetic abstracts without crash; report avg score latency.

---

## 12. Escalation

1. Check Audit trail for the article/search run.
2. Check Jobs for failed background work.
3. Check `/api/metrics` for error spikes.
4. Preserve DB backup before any schema/env experiments.

See also: [parallel_run_protocol.md](parallel_run_protocol.md), [model_card.md](model_card.md), [pubmed.md](pubmed.md).
