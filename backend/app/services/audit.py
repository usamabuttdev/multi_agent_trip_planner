from __future__ import annotations

from datetime import datetime, timezone
from uuid import uuid4

from sqlalchemy.orm import Session

from app.models.tables import AgentRun, Request


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def create_request(session: Session, user_query: str) -> Request:
    row = Request(id=str(uuid4()), user_query=user_query, status="pending")
    session.add(row)
    session.commit()
    session.refresh(row)
    return row


def start_agent_run(session: Session, request_id: str, agent_name: str, input_payload: str | None) -> AgentRun:
    row = AgentRun(
        request_id=request_id,
        agent_name=agent_name,
        status="running",
        input_json=input_payload,
        started_at=_utcnow(),
    )
    session.add(row)
    session.commit()
    session.refresh(row)
    return row


def finish_agent_run(
    session: Session,
    run: AgentRun,
    *,
    status: str,
    output_payload: str | None = None,
    error: str | None = None,
) -> AgentRun:
    run.status = status
    run.output_json = output_payload
    run.error = error
    run.ended_at = _utcnow()
    session.add(run)
    session.commit()
    session.refresh(run)
    return run


def finish_request(
    session: Session,
    request: Request,
    *,
    status: str,
    route_json: str | None,
    final_answer: str | None,
    duration_ms: int,
    error: str | None = None,
) -> Request:
    request.status = status
    request.route_json = route_json
    request.final_answer = final_answer
    request.duration_ms = duration_ms
    request.error = error
    session.add(request)
    session.commit()
    session.refresh(request)
    return request
