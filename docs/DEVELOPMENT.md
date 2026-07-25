# Development guide

## Monorepo layout

```
litmon-pv/
├── apps/
│   ├── api/                 # FastAPI (Python)
│   │   ├── app/
│   │   │   ├── api/         # routes, deps
│   │   │   ├── core/        # config, db, auth, metrics, logging
│   │   │   ├── models/      # SQLAlchemy entities
│   │   │   ├── schemas/     # Pydantic
│   │   │   ├── services/    # domain logic
│   │   │   ├── bootstrap.py # seed users/product
│   │   │   └── main.py      # app entry + lifespan
│   │   ├── tests/
│   │   └── requirements.txt
│   └── web/                 # React + Vite + TypeScript
│       └── src/
│           ├── pages/       # Queues, Article, Admin, Ops, Archive, Audit
│           ├── api.ts       # fetch client
│           └── App.tsx      # routes
├── data/seed/               # gold_labels.json
├── docs/                    # this documentation
├── workers/                 # scheduled_search, perf_smoke
├── .env.example
└── docker-compose.yml
```

## Design principles (do not break)

1. **Human final decision** on anything that could be a reportable case.  
2. **Never silent-delete** literature hits — archive + audit + recall.  
3. **Over-flag** rather than under-flag (sensitivity &gt; specificity).  
4. **Explainability** — scores need reason tags, not black boxes.  
5. **Version everything that affects routing** — prompt/ruleset/threshold on each score.  
6. **Export only** to case systems in pilot (no Argus API).

## Backend conventions

- Domain logic in `app/services/*`, not fat route handlers.  
- Append-only screening results (rescore creates new rows).  
- Every significant action → `log_event(...)`.  
- PubMed only via `app/services/pubmed/client.py` (no scraping).  
- Jobs via `enqueue_job` (thread-safe for sync routes).

## Database migrations (Alembic)

Schema is managed with Alembic under `apps/api/alembic/`. On API startup,
`run_migrations()` upgrades to head (or stamps legacy `create_all` DBs).

```bash
cd apps/api
source .venv/bin/activate
export PYTHONPATH="$(pwd)"

# Apply migrations
alembic upgrade head

# After changing models/entities.py
alembic revision --autogenerate -m "describe_change"
# Review the generated file, then:
alembic upgrade head
```

Prefer migrations over relying on `create_all` alone so schema stays consistent
across laptops. `create_all` remains a last-resort fallback if Alembic fails.

## Frontend conventions

- All HTTP via `src/api.ts`.  
- Auth token in `localStorage` (`litmon_token`).  
- Keep article decision path fast (target &lt; 60s for typical review).  
- Show AI reasoning on the article side panel always.

## Running tests

```bash
cd apps/api
# activate venv + PYTHONPATH
python -m pytest tests -q
```

Key suites:

- `test_triage.py` — routing bands / hard rules  
- `test_pubmed_parse.py` — EFetch XML  
- `test_evaluation.py` — gold sensitivity  
- `test_sla.py` — overdue detection  

## Useful scripts

```bash
# Weekly-style PubMed pull
python workers/scheduled_search.py --days 7 --max-fetch 50

# Score throughput smoke
python workers/perf_smoke.py --n 500
```

(Run from `apps/api` with venv + `PYTHONPATH`.)

## Branching suggestion

```text
main              # stable pilot
feature/<topic>   # work in progress
fix/<issue>        # bugfix
```

Open PRs into `main`. Keep commits focused.

## Secrets checklist before push

- [ ] No `.env`  
- [ ] No `litmon.db`  
- [ ] No API keys in source or docs  
- [ ] Demo passwords only documented as local pilot defaults  

## Version stamp

API reports `version` in `/health` (currently `0.2.1`). Bump when releasing meaningful pilot milestones; note in [CHANGELOG.md](CHANGELOG.md).
