# Architecture (Phase 1 Pilot)

## Pipeline

```text
┌─────────────┐   ┌──────────────┐   ┌────────────────┐   ┌─────────────┐
│ 1. Search   │──▶│ 2. Ingest &  │──▶│ 3. AI Screen   │──▶│ 4. Triage   │
│ PubMed API  │   │ Dedup PMID   │   │ Score+explain  │   │ Rules+SLA   │
└─────────────┘   └──────────────┘   └────────────────┘   └──────┬──────┘
                                                                  │
                    ┌──────────────┐   ┌────────────────┐         │
                    │ 6. Export    │◀──│ 5. Reviewer    │◀────────┘
                    │ JSON/CSV     │   │ Human decision │
                    └──────────────┘   └────────────────┘
```

Nothing is discarded silently. Auto-Clear is logged and 10% QC sampled; archive is recallable.

## Service components

| Component | Path | Role |
|-----------|------|------|
| API gateway | `app/main.py`, `app/api/routes.py` | REST, auth, CORS |
| Search orchestrator | `services/pipeline.py` + `pubmed/` | Scheduled/manual PubMed runs |
| AI screening | `services/ai/scorer.py` | Mock heuristic or LLM JSON |
| Triage engine | `services/triage/engine.py` | Bands + hard rules |
| Jobs worker | `services/jobs.py` | In-process asyncio queue |
| Notifications | `services/notifications.py` | Log + optional SMTP |
| Reviewer UI | `apps/web` | Queues, article, admin, ops |

## Data store

- Default: **SQLite** file `apps/api/litmon.db` (local pilot)  
- Optional: **PostgreSQL** via `DATABASE_URL`  
- Tables created on startup / bootstrap (`Base.metadata.create_all`)  
- Core entities: Product, SearchString, SearchRun, Article, ScreeningResult, TriageAssignment, ReviewDecision, ExportPackage, AuditEvent, Job, User  

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

Local: API :8000 + Vite :5173.  
Optional: `docker compose` for Postgres/Redis only.  
No production container image is mandated yet.
