# Architecture (partner-feedback MVP)

## Pipeline

```text
┌─────────────┐   ┌──────────────┐   ┌────────────────┐   ┌─────────────┐
│ 1. Search   │──▶│ 2. Ingest &  │──▶│ 3. AI Screen   │──▶│ 4. Workflow │
│ PubMed API  │   │ Dedup PMID   │   │ Score+explain  │   │ + alerts    │
└─────────────┘   └──────────────┘   └────────────────┘   └──────┬──────┘
                                                                  │
                    ┌──────────────┐   ┌────────────────┐         │
                    │ 6. Regulatory│◀──│ 5. Reviewer    │◀────────┘
                    │ output/store │   │ Human decision │
                    └──────────────┘   └────────────────┘
```

Nothing is discarded silently. Auto-Clear is logged and 10% QC sampled; archive is recallable.

## Service components

| Component | Path | Role |
|-----------|------|------|
| API gateway | `app/main.py`, `app/api/routes.py` | REST, auth, CORS |
| Search orchestrator | `services/pipeline.py` + `pubmed/` | Manual and recurring PubMed runs |
| AI screening | `services/ai/scorer.py` | Mock heuristic or LLM JSON |
| Triage engine | `services/triage/engine.py` | Bands + hard rules |
| Jobs worker | `services/jobs.py` | In-process asyncio queue |
| Alerts and schedules | `services/triggers.py`, `services/schedules.py` | Persistent in-app alerts; recurring searches and time-driven checks |
| Reviewer UI | `apps/web` | Dashboard, workspace, detection report, alerts, submission/storage, administration and ops |

## Data store

- Default: **SQLite** file `apps/api/litmon.db` (local pilot)
- Optional: **PostgreSQL** via `DATABASE_URL`
- Schema maintained with Alembic migrations at API startup / bootstrap
- Core entities: Product, LiteratureSource, SearchString, SearchSchedule, SearchRun, Article, ScreeningResult, TriageAssignment, ReviewDecision, RegulatoryRecord, Alert, ExportPackage, AuditEvent, Job, User

## Auth & roles

JWT bearer tokens. Roles: `reviewer`, `senior_reviewer`, `pv_lead`, `admin`.

## AI scoring dimensions

| Dimension | Meaning |
|-----------|---------|
| `product_match` | Monitored substance/brand in article |
| `event_relevance` | ADR / safety outcome vs efficacy-only |
| `icsr_criteria_match` | Patient, drug, event, reporter present |
| `composite` | Weighted combination for routing |

Each score stores reason tags + model/prompt/ruleset/threshold versions.

## Literature source

**PubMed only** via NCBI E-utilities (see [pubmed.md](pubmed.md)). Embase/out-of-scope for v1.

## Safety posture

| Risk | Mitigation |
|------|------------|
| Silent false negatives | Over-flag; no silent delete; QC sample; sensitivity KPI |
| LLM hallucination | Evidence tags; human checklist authoritative |
| Audit gaps | Append-only audit events on key actions |
| Unvalidated use | Explicit pilot banner; docs disclaimer |

## Deployment (pilot)

Local pilot: API :8000 + Vite :5173.
PostgreSQL is supported through `DATABASE_URL`; provision it separately for a
shared environment. This repository does **not** currently include Docker
Compose, a container image, CI, or a production scheduler deployment.
