# Trip orchestrator

Internal-style multi-agent trip planner: Destination, Itinerary, and Budget specialists behind a FastAPI + LangGraph orchestrator, with a React 18 UI and an SQLite audit trail.

- [Design decisions](DECISIONS.md) (orchestration, guardrails, what we cut)
- [Azure production architecture](ARCHITECTURE.md) (500+ concurrent users)
- Longer working notes: [NOTES.md](NOTES.md)

## How to run

**Need:** Python 3.12, Node 20+, an [OpenRouter](https://openrouter.ai/settings/keys) key (free models are fine).

```bash
cp .env.example .env   # set OPENROUTER_API_KEY
```

Optional: `OPENROUTER_MODEL` (default `openrouter/free`).

Backend:

```bash
cd backend
python3 -m venv .venv
source .venv/bin/activate   # Windows: .venv\Scripts\activate
pip install -r requirements.txt
uvicorn app.main:app --reload --port 8000
```

Frontend (separate terminal):

```bash
cd frontend
npm install
npm run dev
```

Open http://localhost:5173. Vite proxies `/api` to port 8000.

Try: *Five day trip somewhere warm in Europe for under 1500 pounds* (full chain) and *3 days in Lisbon under 800 euros* (skip Destination). History rows reopen the stored trace; `?role=operator` is an auth stub only.

```bash
cd backend && PYTHONPATH=. .venv/bin/python -m unittest tests.test_core
```

## Environment variables (local and Vercel)

Pydantic Settings reads **process env first**. A local `.env` is only for development. On Vercel you never commit keys — you paste them in the dashboard. Vite bakes `VITE_*` in at **build** time, so change those and Redeploy.

### FastAPI project (Vercel)

Project → Settings → Environment Variables, Production + Preview:

| Name | Required | Notes |
| --- | --- | --- |
| `OPENROUTER_API_KEY` | yes | Same key as local `.env` |
| `OPENROUTER_MODEL` | no | Default `openrouter/free` |
| `OPENROUTER_BASE_URL` | no | Default `https://openrouter.ai/api/v1` |
| `FRONTEND_ORIGIN` | recommended | Frontend origin, e.g. `https://your-ui.vercel.app` (or `*` for a demo) |
| `DATABASE_URL` | no | On Vercel, SQLite defaults to `/tmp/trips.db` (ephemeral). Use Postgres later if you want a lasting audit log. |

Vercel injects these as `os.environ`. [backend/app/config.py](backend/app/config.py) picks them up automatically (`VERCEL=1` is set by the platform).

### Frontend project (Vercel)

| Name | Required | Notes |
| --- | --- | --- |
| `VITE_API_URL` | yes on Vercel | Public FastAPI URL, **no trailing slash**, e.g. `https://your-api.vercel.app` |

Local: `cp frontend/.env.example frontend/.env` and set `VITE_API_URL` to your deployed API (or leave empty for the :8000 proxy). Restart `npm run dev` after changing it. On Vercel, set the same name in the **frontend** project, then Redeploy — Vite inlines it at build time ([frontend/src/config.ts](frontend/src/config.ts)).

