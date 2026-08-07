# LitMon-PV

**Literature Monitoring Automation for Pharmacovigilance**

AI-assisted, human-in-the-loop pipeline for systematic literature review (SLR), ICSR case detection, and signal-relevant article triage.

[![Status](https://img.shields.io/badge/status-partner%20MVP-blue)](.)
[![Not GxP](https://img.shields.io/badge/GxP-not%20validated-orange)](.)

> **Core principle:** Automate search and first-pass triage; keep a qualified human as the final decision-maker. The AI ranks, flags, and explains — it never silently discards a potentially reportable article without an audit trail.

---

## Features (partner-feedback MVP)

- **PubMed search** via NCBI E-utilities (free public API — not scraping)
- **Dedup** by PMID/DOI across runs
- **AI screening** — product match, event relevance, ICSR criteria + reason tags
  (mock heuristic offline; real LLM via OpenAI-compatible API)
- **Triage queues** — Auto-Clear (with QC sample), Standard, Priority, Expedited + SLAs
- **Product-based reviewer assignment** — responsible reviewer routing, My Work, and reassignment
- **Signal workflow** — human-controlled potential / confirmed / rejected signal status
- **PV dashboard & alert inbox** — all Step-12 measures, drill-through filters, and eight persistent in-app alert triggers
- **Reviewer workspace** — nine workflow folders and ten PV filters, with priority-driven sorting
- **Detection report** — structured extraction, AI and human classification, signal tags, ICSR checklist, decision/audit history, and print/save output
- **Submission & storage** — data-driven mandatory-field validation, versioned prototype XML, download, submit-or-retain decision, and manual gateway evidence
- **Product/source/schedule administration** — explicit product licence facts, APIs, responsible reviewer, source/provider separation, recurring searches, and exception summary
- **Archive & recall** — reversible, searchable
- **Imports** — PMID list or CSV (backup if PubMed is down)
- **Exports** — ICSR handoff + parallel-run comparison (JSON/CSV)
- **Evaluation** — gold-label sensitivity harness
- **Ops** — metrics, background jobs, and automated time-driven SLA checks
- **Audit trail** — filterable, CSV-exportable inspection-oriented event log

---

## Quick start

### Prerequisites

- Python 3.11+
- Node.js 18+
- Git

### Clone

```bash
git clone https://github.com/namit-jpg/litmon-pv.git
cd litmon-pv
cp .env.example .env
# Edit .env — at least set NCBI_EMAIL for live PubMed; set JWT_SECRET
```

### Backend

```powershell
# Windows PowerShell
cd apps\api
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
$env:PYTHONPATH = (Get-Location).Path
python -m app.bootstrap
uvicorn app.main:app --reload --port 8000
```

```bash
# macOS / Linux
cd apps/api
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
export PYTHONPATH="$(pwd)"
python -m app.bootstrap
uvicorn app.main:app --reload --port 8000
```

- API: http://127.0.0.1:8000
- OpenAPI: http://127.0.0.1:8000/docs

### Frontend

```bash
cd apps/web
npm install
npm run dev
```

- App: http://localhost:5173

### Demo logins

| Email | Password | Role |
|-------|----------|------|
| `admin@litmon.local` | `admin123` | Admin |
| `reviewer@litmon.local` | `reviewer123` | Reviewer |
| `pvlead@litmon.local` | `pvlead123` | PV Lead |

After login, add or select a monitored drug under **Product search**, assign its
responsible reviewer under **Products**, and run a bounded PubMed search.

Manual MVP test: [docs/phase3_4_manual_test.md](docs/phase3_4_manual_test.md)

**Full setup (new laptop):** [docs/SETUP.md](docs/SETUP.md)

---

## Documentation

| Doc | Description |
|-----|-------------|
| [docs/README.md](docs/README.md) | Doc index |
| [docs/SETUP.md](docs/SETUP.md) | New machine setup |
| [docs/AGENTS.md](docs/AGENTS.md) | **For AI agents** — handoff context |
| [docs/API.md](docs/API.md) | REST API map |
| [docs/DEVELOPMENT.md](docs/DEVELOPMENT.md) | Dev conventions |
| [docs/architecture.md](docs/architecture.md) | System architecture |
| [docs/pilot_runbook.md](docs/pilot_runbook.md) | PV operations runbook |
| [docs/pubmed.md](docs/pubmed.md) | PubMed E-utilities |
| [docs/model_card.md](docs/model_card.md) | Screening model card |
| [docs/parallel_run_protocol.md](docs/parallel_run_protocol.md) | Manual parallel-run protocol |
| [docs/phase3_4_manual_test.md](docs/phase3_4_manual_test.md) | Phase 3/4 manual functional test |
| [docs/CHANGELOG.md](docs/CHANGELOG.md) | Version history |

---

## Stack

| Layer | Tech |
|-------|------|
| API | Python, FastAPI, SQLAlchemy 2, Pydantic v2 |
| DB | SQLite (default) or PostgreSQL |
| Web | React 18, TypeScript, Vite |
| Literature | NCBI PubMed E-utilities |
| AI | Heuristic mock **or** OpenAI-compatible LLM |
| Jobs | In-process asyncio worker |

---

## Pipeline

```text
PubMed → Ingest/Dedup → AI score + explain → Triage/SLA → Human review → Export
```

---

## Project layout

```text
litmon-pv/
├── apps/api/          # Backend
├── apps/web/          # Reviewer UI
├── data/seed/         # Gold labels
├── docs/              # Documentation
├── workers/           # scheduled_search, perf_smoke
├── .env.example
└── README.md
```

---

## Environment variables

See [`.env.example`](.env.example). Important keys:

| Variable | Purpose |
|----------|---------|
| `NCBI_EMAIL` | Required by NCBI policy |
| `NCBI_API_KEY` | Optional; higher rate limit |
| `LLM_MOCK` | `true` = offline heuristic scorer |
| `LLM_API_KEY` / `LLM_BASE_URL` / `LLM_MODEL` | Real LLM |
| `JWT_SECRET` | **Change in any shared env** |
| `DATABASE_URL` | SQLite default or Postgres URL |

---

## Tests

```bash
cd apps/api
# venv + PYTHONPATH
python -m pytest tests -q
```

---

## Working with another agent / laptop

1. Clone this repo on the other machine ([SETUP.md](docs/SETUP.md)).
2. Point the agent at **[docs/AGENTS.md](docs/AGENTS.md)** for context.
3. Use feature branches and pull requests.
4. Never commit `.env`, databases, or API keys.

---

## Regulatory note

Informed by EU GVP Module VI, FDA 21 CFR 314.80, and ICH E2D case validity concepts.

**This is not a validated GxP system.** Production use requires formal computer system validation (CSV), SOPs, and Quality/Regulatory approval.

---

## License

MIT — see [LICENSE](LICENSE). Use at your own risk for evaluation only.
