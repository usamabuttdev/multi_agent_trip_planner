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
