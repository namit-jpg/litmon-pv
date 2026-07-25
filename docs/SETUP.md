# Setup on a new machine

Use this when cloning the GitHub repo onto another laptop (or spinning up a second agent environment).

## Prerequisites

| Tool | Version | Notes |
|------|---------|-------|
| Git | 2.x+ | Clone the repo |
| Python | 3.11+ (3.12–3.14 ok) | Backend |
| Node.js | 18+ (20+ recommended) | Frontend |
| NCBI email | any valid email | Required for live PubMed |
| (Optional) NCBI API key | free | [NCBI account](https://www.ncbi.nlm.nih.gov/account/) |
| (Optional) LLM API key | OpenAI-compatible | Real AI scoring; mock works offline |

Docker is **optional** (Postgres via `docker-compose.yml`). Default DB is SQLite.

---

## 1. Clone

```bash
git clone https://github.com/namit-jpg/litmon-pv.git
cd litmon-pv
```

If the remote name differs, use your fork URL.

---

## 2. Environment file

```bash
# from repo root
cp .env.example .env
```

**Minimum edits for live PubMed:**

```env
NCBI_EMAIL=you@company.com
NCBI_API_KEY=          # optional but recommended
JWT_SECRET=use-a-long-random-string-here
```

**Offline / demo (default):**

```env
LLM_MOCK=true
# NCBI_EMAIL still set (client always sends it)
```

**Real LLM scoring:**

```env
LLM_MOCK=false
LLM_API_KEY=sk-...
LLM_BASE_URL=https://api.x.ai/v1
LLM_MODEL=grok-2-latest
```

Never commit `.env`. Only `.env.example` is in git.

---

## 3. Backend

### Windows (PowerShell)

```powershell
cd apps\api
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
$env:PYTHONPATH = (Get-Location).Path
python -m app.bootstrap
uvicorn app.main:app --reload --host 127.0.0.1 --port 8000
```

### macOS / Linux

```bash
cd apps/api
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
export PYTHONPATH="$(pwd)"
python -m app.bootstrap
uvicorn app.main:app --reload --host 127.0.0.1 --port 8000
```

Check:

- http://127.0.0.1:8000/health → `{"status":"ok",...}`
- http://127.0.0.1:8000/docs → OpenAPI UI

---

## 4. Frontend

```bash
cd apps/web
npm install
npm run dev
```

Open http://localhost:5173  

Vite proxies `/api` → `http://127.0.0.1:8000`.

---

## 5. Login (seeded users)

| Email | Password | Role |
|-------|----------|------|
| `reviewer@litmon.local` | `reviewer123` | Reviewer |
| `pvlead@litmon.local` | `pvlead123` | PV Lead |
| `admin@litmon.local` | `admin123` | Admin |
| `senior@litmon.local` | `senior123` | Senior reviewer |

Change these before any shared/pilot environment.

---

## 6. First actions after setup

1. Sign in as **admin**  
2. **Admin → Seed demo articles** (offline path)  
3. Open **Queues** → triage a few cards  
4. Optional: set `NCBI_EMAIL` and **Run PubMed search**  
5. Optional: **Ops** for metrics / SLA  

---

## 7. Tests

```bash
cd apps/api
source .venv/bin/activate   # or Windows Activate.ps1
export PYTHONPATH="$(pwd)"  # or $env:PYTHONPATH on Windows
python -m pytest tests -q
```

---

## 8. Optional Postgres

```bash
# requires Docker
docker compose up -d db
```

```env
DATABASE_URL=postgresql+psycopg://litmon:litmon@localhost:5432/litmon
```

Re-run bootstrap against the new DB.

---

## 9. Common issues

| Problem | Fix |
|---------|-----|
| `ModuleNotFoundError: app` | Set `PYTHONPATH` to `apps/api` |
| Login fails after clone | Run `python -m app.bootstrap` |
| PubMed 429 / errors | Add `NCBI_API_KEY`; check email |
| CORS errors | Ensure API on 8000 and web on 5173; check `CORS_ORIGINS` |
| Frontend can’t reach API | API must be running; proxy is in `vite.config.ts` |
| Port 8000 in use | Stop other uvicorn or change `--port` |

---

## 10. Cross-laptop collaboration

1. Work on feature branches: `git checkout -b feature/my-work`  
2. Push and open PRs on GitHub  
3. Never push `.env`, `*.db`, or API keys  
4. Point the other agent at [AGENTS.md](AGENTS.md) for project context  
