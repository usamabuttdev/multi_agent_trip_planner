from __future__ import annotations

import json
import os
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any

from fastapi import Depends, FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from sqlalchemy.orm import Session, joinedload

from app.config import get_settings
from app.db import SessionLocal, get_session, init_db
from app.models.contracts import TripCreateRequest, TripDetail, TripResponse, TripSummary
from app.models.tables import AgentRun, Request
from app.services.audit import create_request
from app.services.runner import iter_trip_events, run_trip, state_to_response


@asynccontextmanager
async def lifespan(_app: FastAPI):
    init_db()
    yield


settings = get_settings()
app = FastAPI(
    title="Trip Orchestrator",
    version="0.1.0",
    lifespan=lifespan,
    # OPTIONS preflight must not 307; Vercel + FastAPI slash redirects fail CORS.
    redirect_slashes=False,
)

_raw_origins = [origin.strip() for origin in settings.frontend_origin.split(",") if origin.strip()]
_wildcard = _raw_origins == ["*"]
_explicit = [] if _wildcard else _raw_origins
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:5173",
        "http://127.0.0.1:5173",
        *_explicit,
    ],
    allow_origin_regex=r"https://.*\.vercel\.app",
    allow_credentials=False,
    allow_methods=["GET", "POST", "OPTIONS", "PUT", "PATCH", "DELETE"],
    allow_headers=["*"],
    expose_headers=["*"],
    max_age=86400,
)


def _require_llm_key() -> None:
    if not settings.openrouter_api_key:
        raise HTTPException(
            status_code=503,
            detail="OPENROUTER_API_KEY is not configured. Copy .env.example to .env and add an OpenRouter key.",
        )


def _agents_from_row(row: Request) -> list[str]:
    specialists = {"destination", "itinerary", "budget"}
    from_runs = [run.agent_name for run in row.agent_runs if run.agent_name in specialists]
    if from_runs:
        return from_runs
    if not row.route_json:
        return []
    try:
        route = json.loads(row.route_json)
        return [name for name in route if name in specialists]
    except json.JSONDecodeError:
        return []


@app.get("/api/health")
def health() -> dict[str, Any]:
    return {
        "ok": True,
        "model": settings.openrouter_model,
        "llm_configured": bool(settings.openrouter_api_key),
    }


@app.post("/api/trips", response_model=TripResponse)
async def create_trip(body: TripCreateRequest, session: Session = Depends(get_session)) -> TripResponse:
    _require_llm_key()
    query = body.query.strip()
    row = create_request(session, query)
    name, payload = await run_trip(session, row, query)
    if name == "result":
        return TripResponse.model_validate(payload)
    message = payload.get("message") or "Orchestration failed"
    raise HTTPException(status_code=502, detail=message)


@app.post("/api/trips/stream")
async def stream_trip(body: TripCreateRequest) -> StreamingResponse:
    _require_llm_key()
    session = SessionLocal()
    query = body.query.strip()
    row = create_request(session, query)

    async def events():
        try:
            async for name, payload in iter_trip_events(session, row, query):
                data = json.dumps(payload, default=str)
                yield f"event: {name}\ndata: {data}\n\n"
        finally:
            session.close()

    return StreamingResponse(
        events(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
            "Access-Control-Allow-Origin": "*",
        },
    )


@app.get("/api/trips", response_model=list[TripSummary])
def list_trips(session: Session = Depends(get_session), limit: int = 20) -> list[TripSummary]:
    rows = (
        session.query(Request)
        .options(joinedload(Request.agent_runs))
        .order_by(Request.created_at.desc())
        .limit(min(limit, 50))
        .all()
    )
    return [
        TripSummary(
            id=row.id,
            created_at=row.created_at.isoformat() if row.created_at else "",
            user_query=row.user_query,
            agents=_agents_from_row(row),
            status=row.status,
            duration_ms=row.duration_ms,
            error=row.error,
        )
        for row in rows
    ]


@app.get("/api/trips/{request_id}", response_model=TripDetail)
def get_trip(request_id: str, session: Session = Depends(get_session)) -> TripDetail:
    row = (
        session.query(Request)
        .options(joinedload(Request.agent_runs))
        .filter(Request.id == request_id)
        .first()
    )
    if not row:
        raise HTTPException(status_code=404, detail="Request not found")
    parsed_state: dict[str, Any] = {
        "request_id": row.id,
        "final_answer": row.final_answer,
        "route": json.loads(row.route_json) if row.route_json else [],
        "agent_trace": [
            {
                "agent": run.agent_name,
                "status": run.status,
                "summary": "",
                "error": run.error,
            }
            for run in row.agent_runs
        ],
    }
    for run in row.agent_runs:
        if not run.output_json:
            continue
        try:
            payload = json.loads(run.output_json)
        except json.JSONDecodeError:
            continue
        if "parsed" in payload:
            parsed_state["parsed"] = payload["parsed"]
        if "destination_result" in payload:
            parsed_state["destination_result"] = payload["destination_result"]
        if "itinerary_result" in payload:
            parsed_state["itinerary_result"] = payload["itinerary_result"]
        if "budget_result" in payload:
            parsed_state["budget_result"] = payload["budget_result"]
        if "final_answer" in payload and payload["final_answer"]:
            parsed_state["final_answer"] = payload["final_answer"]
    response = state_to_response(parsed_state, status=row.status, error=row.error)
    return TripDetail(
        **response.model_dump(),
        user_query=row.user_query,
        created_at=row.created_at.isoformat() if row.created_at else "",
        duration_ms=row.duration_ms,
        agent_runs=[
            {
                "id": run.id,
                "agent_name": run.agent_name,
                "status": run.status,
                "started_at": run.started_at.isoformat() if run.started_at else None,
                "ended_at": run.ended_at.isoformat() if run.ended_at else None,
                "error": run.error,
            }
            for run in row.agent_runs
        ],
    )


@app.get("/api/metrics")
def metrics(session: Session = Depends(get_session)) -> dict[str, Any]:
    rows = session.query(Request).all()
    runs = session.query(AgentRun).all()
    by_status: dict[str, int] = {}
    for row in rows:
        by_status[row.status] = by_status.get(row.status, 0) + 1
    by_agent: dict[str, int] = {}
    errors = 0
    for run in runs:
        by_agent[run.agent_name] = by_agent.get(run.agent_name, 0) + 1
        if run.status == "error":
            errors += 1
    return {
        "requests": len(rows),
        "by_status": by_status,
        "agent_runs": by_agent,
        "agent_errors": errors,
    }


def _frontend_dir() -> Path | None:
    candidates = []
    env_dir = os.getenv("FRONTEND_DIST")
    if env_dir:
        candidates.append(Path(env_dir))
    here = Path(__file__).resolve()
    candidates.extend(
        [
            here.parents[2] / "frontend" / "dist",
            here.parents[1] / "frontend_dist",
            here.parents[1] / "static",
        ]
    )
    for candidate in candidates:
        if (candidate / "index.html").is_file():
            return candidate
    return None


frontend_root = _frontend_dir()
if frontend_root is not None:
    assets = frontend_root / "assets"
    if assets.is_dir():
        app.mount("/assets", StaticFiles(directory=assets), name="assets")

    spa_root = frontend_root

    @app.get("/{path:path}")
    def frontend_spa(path: str):
        if path.startswith("api/"):
            raise HTTPException(status_code=404, detail="Not found")
        file_path = spa_root / path
        if file_path.is_file():
            return FileResponse(file_path)
        return FileResponse(spa_root / "index.html")

