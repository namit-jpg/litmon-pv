# Guide for AI coding agents

You are working on **LitMon-PV** — Literature Monitoring Automation for Pharmacovigilance.

## What this system is

An AI-assisted, **human-in-the-loop** pipeline that:

1. Searches **PubMed** (NCBI E-utilities API only — free, no scraping)
2. Deduplicates by PMID/DOI
3. Scores abstracts (product match, event relevance, ICSR criteria) with reason tags
4. Routes to queues (Auto-Clear / Standard / Priority / Expedited) with SLAs
5. Lets PV reviewers confirm ICSR vs not-a-case with an explicit 4-criteria checklist
6. Exports structured packages for case management (no direct Argus integration)

**Regulatory posture:** Pilot / prototype only — not GxP validated. Prefer over-flagging. Never silently discard potentially reportable articles.

## Repo root

After clone, the monorepo root contains `apps/`, `docs/`, `workers/`, `data/`.

## Where to change what

| Need | Location |
|------|----------|
| HTTP endpoints | `apps/api/app/api/routes.py` |
| Auth / RBAC | `apps/api/app/api/deps.py`, `core/security.py` |
| DB models | `apps/api/app/models/entities.py` |
| PubMed client | `apps/api/app/services/pubmed/client.py` |
| AI scoring | `apps/api/app/services/ai/scorer.py` |
| Triage thresholds | `apps/api/app/services/triage/engine.py` |
| Search/score pipeline | `apps/api/app/services/pipeline.py` |
| Background jobs | `apps/api/app/services/jobs.py` |
| React pages | `apps/web/src/pages/*` |
| API client (web) | `apps/web/src/api.ts` |
| Env defaults | `.env.example`, `apps/api/app/core/config.py` |

## Local run (agent checklist)

1. Copy `.env.example` → `.env`
2. `apps/api`: venv, `pip install -r requirements.txt`, `PYTHONPATH=.`, `python -m app.bootstrap`, `uvicorn app.main:app --port 8000`
3. `apps/web`: `npm install`, `npm run dev`
4. Tests: `pytest tests -q` from `apps/api`

Default admin: `admin@litmon.local` / `admin123`

## Non-negotiables

- Do **not** add Embase scraping or PubMed HTML scraping.
- Do **not** auto-finalize ICSR without human action.
- Do **not** hard-delete articles; use status + archive + recall.
- Do **not** commit secrets, `.env`, or `*.db`.
- Keep screening dimensions separate (product / event / icsr), not a single opaque score only.
- Log model/prompt/ruleset/threshold versions on every score.

## Out of scope (unless user explicitly expands)

- Argus / ArisGlobal live integration
- Multi-tenant SaaS
- Formal GxP CSV package
- Social media listening
- Full native multi-language NLP

## Docs to read first

1. [SETUP.md](SETUP.md)
2. [architecture.md](architecture.md)
3. [API.md](API.md)
4. [pilot_runbook.md](pilot_runbook.md)

## Partner-feedback MVP status

Phases 1–4 of the approved partner-feedback MVP are implemented. **Before
starting any feature work, read [MVP_BUILD_BRIEF.md](MVP_BUILD_BRIEF.md)** — it
defines the current architecture and supersedes the historical backlog below.
The manual functional rehearsal is intentionally user-owned and remains in
[phase3_4_manual_test.md](phase3_4_manual_test.md); do not claim it has been
performed unless its evidence is supplied.

- [MVP_BUILD_BRIEF.md](MVP_BUILD_BRIEF.md) — phased implementation plan, open questions
- [partner_feedback.md](partner_feedback.md) — the requirements themselves
- [wireframes/mvp-wireframe.html](wireframes/mvp-wireframe.html) — approved wireframe, 9 screens,
  with per-element build notes. Open in a browser. **This is the design authority.**

Headline: the app is now a PV literature-monitoring platform over the existing
search/scoring engine. Classification, workflow status, signal tags and
regulatory disposition are separate. Alerts are persistent in-app records only;
outbound notification channels are intentionally not implemented.

## Post-MVP options — not current implementation work

Do not reopen these unless the user explicitly expands scope:

- Browser-level regression coverage for login → search → review → regulatory export
- Automatic comparison of parallel-run exports after manual CSV re-upload
- Production deployment packaging, a singleton scheduler/worker, CI, and an operational runbook
- Expanded evaluation labels and PV-owner threshold calibration

## Architecture one-liner

```text
PubMed E-utilities → Ingest/Dedup → LLM/heuristic score → Rules triage → React reviewer → Export JSON/CSV
```
