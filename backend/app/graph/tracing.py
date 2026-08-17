from __future__ import annotations

from typing import Any

from app.graph.state import AgentError, TraceStep, TripState


def append_trace(state: TripState, step: TraceStep) -> list[TraceStep]:
    return [*state.get("agent_trace", []), step]


def append_error(state: TripState, agent: str, error: str) -> list[AgentError]:
    return [*state.get("errors", []), {"agent": agent, "error": error}]


def mark_contributed(state: TripState, agent: str) -> list[str]:
    current = list(state.get("contributing_agents") or [])
    if agent not in current:
        current.append(agent)
    return current


def parsed_dict(state: TripState) -> dict[str, Any]:
    return state.get("parsed") or {}
