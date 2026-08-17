from __future__ import annotations

import json
import time
from collections.abc import AsyncIterator
from typing import Any, Literal

from sqlalchemy.orm import Session

from app.graph.graph import get_graph
from app.graph.state import TripState
from app.models.contracts import (
    AgentTraceStep,
    BudgetOutput,
    DestinationOutput,
    ItineraryOutput,
    PlannerOutput,
    TripResponse,
)
from app.models.tables import Request
from app.services.audit import finish_agent_run, finish_request, start_agent_run

EventName = Literal["start", "agent", "result", "error"]
SPECIALISTS = ("destination", "itinerary", "budget")


def empty_state(request_id: str, query: str) -> TripState:
    return {
        "request_id": request_id,
        "user_query": query,
        "parsed": None,
        "route": [],
        "destination_result": None,
        "itinerary_result": None,
        "budget_result": None,
        "agent_trace": [],
        "errors": [],
        "final_answer": None,
        "contributing_agents": [],
    }


def contributing_specialists(state: TripState) -> list[str]:
    agents: list[str] = []
    ordered = list(state.get("route") or []) or list(SPECIALISTS)
    for name in ordered:
        if name in SPECIALISTS and state.get(f"{name}_result") and name not in agents:
            agents.append(name)
    return agents


def state_to_response(state: TripState, *, status: str, error: str | None = None) -> TripResponse:
    parsed = PlannerOutput.model_validate(state["parsed"]) if state.get("parsed") else None
    destination = (
        DestinationOutput.model_validate(state["destination_result"])
        if state.get("destination_result")
        else None
    )
    itinerary = (
        ItineraryOutput.model_validate(state["itinerary_result"]) if state.get("itinerary_result") else None
    )
    budget = BudgetOutput.model_validate(state["budget_result"]) if state.get("budget_result") else None
    trace = [AgentTraceStep.model_validate(step) for step in state.get("agent_trace") or []]
    return TripResponse(
        request_id=state.get("request_id") or "",
        answer=state.get("final_answer") or "",
        agents=contributing_specialists(state),
        status=status,
        parsed=parsed,
        destination=destination,
        itinerary=itinerary,
        budget=budget,
        trace=trace,
        error=error,
    )


def _node_status(node: str, delta: dict[str, Any]) -> tuple[str, str, str | None]:
    for step in reversed(delta.get("agent_trace") or []):
        if step.get("agent") == node:
            return step.get("status") or "ok", step.get("summary") or "", step.get("error")
    errors = delta.get("errors") or []
    if any(item.get("agent") == node for item in errors):
        return "error", f"{node} failed", errors[-1].get("error")
    return "ok", node, None


def _output_payload(delta: dict[str, Any]) -> str:
    keep = {
        key: delta[key]
        for key in (
            "parsed",
            "route",
            "destination_result",
            "itinerary_result",
            "budget_result",
            "final_answer",
        )
        if key in delta
    }
    return json.dumps(keep, default=str)


async def iter_trip_events(
    session: Session, request: Request, query: str
) -> AsyncIterator[tuple[EventName, dict[str, Any]]]:
    graph = get_graph()
    started = time.perf_counter()
    merged: TripState = empty_state(request.id, query)
    yield ("start", {"request_id": request.id})
    try:
        async for update in graph.astream(merged, stream_mode="updates"):
            for node, delta in update.items():
                run = start_agent_run(
                    session,
                    request.id,
                    node,
                    json.dumps({"query": query}) if node == "planner" else None,
                )
                status, summary, error = _node_status(node, delta)
                finish_agent_run(
                    session,
                    run,
                    status=status,
                    output_payload=_output_payload(delta),
                    error=error,
                )
                merged.update(delta)  # type: ignore[typeddict-item]
                yield (
                    "agent",
                    {"agent": node, "status": status, "summary": summary, "error": error},
                )
        errors = merged.get("errors") or []
        has_answer = bool(merged.get("final_answer"))
        if errors and has_answer:
            overall = "completed_with_errors"
        elif errors:
            overall = "error"
        else:
            overall = "completed"
        duration_ms = int((time.perf_counter() - started) * 1000)
        finish_request(
            session,
            request,
            status=overall,
            route_json=json.dumps(merged.get("route") or []),
            final_answer=merged.get("final_answer"),
            duration_ms=duration_ms,
            error=errors[0]["error"] if errors else None,
        )
        yield (
            "result",
            state_to_response(
                merged,
                status=overall,
                error=errors[0]["error"] if errors else None,
            ).model_dump(),
        )
    except Exception as exc:  # noqa: BLE001
        duration_ms = int((time.perf_counter() - started) * 1000)
        finish_request(
            session,
            request,
            status="error",
            route_json=json.dumps(merged.get("route") or []),
            final_answer=merged.get("final_answer"),
            duration_ms=duration_ms,
            error=str(exc),
        )
        yield ("error", {"request_id": request.id, "message": str(exc)})


async def run_trip(session: Session, request: Request, query: str) -> tuple[EventName, dict[str, Any]]:
    last: tuple[EventName, dict[str, Any]] = ("error", {"message": "Graph produced no result"})
    async for event in iter_trip_events(session, request, query):
        last = event
    return last
