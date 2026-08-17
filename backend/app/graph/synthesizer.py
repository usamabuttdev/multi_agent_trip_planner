from __future__ import annotations

import json

from langchain_core.messages import HumanMessage, SystemMessage

from app.graph.llm import ainvoke_text
from app.graph.state import TripState
from app.graph.tracing import append_error, append_trace

SYNTH_SYSTEM = """You are the synthesizer for a trip-planning platform.

Write ONE coherent answer for the traveller from the specialist outputs.

Rules:
- Do not invent facts the agents did not provide.
- If Destination contributed, lead with the primary pick and why it fits, then mention alternatives.
- If a destination was rejected for a hard constraint, mention that refusal briefly (transparency).
- If Itinerary contributed, summarise the days; keep it scannable.
- If Budget contributed, state the total vs the cap clearly. If over, state the overage and the cheaper alternative. Never imply it fits when it does not.
- If an agent failed, say what is missing rather than filling the gap with guesses.
- Only name specialists that actually returned a result. Closing line e.g. "Agents: Destination, Itinerary, Budget."
- Plain prose. Short paragraphs. Bullet lists are fine. Do not wrap the answer in JSON.
"""


def _fallback_answer(state: TripState) -> str:
    parts: list[str] = []
    dest = state.get("destination_result")
    if dest and dest.get("primary"):
        parts.append(f"Suggested destination: {dest['primary']}.")
    itin = state.get("itinerary_result")
    if itin:
        parts.append(f"{itin.get('destination')}: {len(itin.get('days') or [])} day plan.")
    budget = state.get("budget_result")
    if budget:
        parts.append(f"Estimated total: {budget.get('total')} {budget.get('currency')}.")
        if budget.get("user_budget") is not None and not budget.get("within_budget"):
            parts.append(
                f"This exceeds the budget of {budget.get('user_budget')} by {budget.get('overage')}."
            )
    errors = state.get("errors") or []
    if errors:
        parts.append(
            "Some agents failed: "
            + "; ".join(f"{e['agent']}: {e['error']}" for e in errors if e.get("agent") != "synthesizer")
        )
    specialists = [name for name in (state.get("route") or []) if state.get(f"{name}_result")]
    if specialists:
        parts.append("Agents: " + ", ".join(name.title() for name in specialists) + ".")
    return " ".join(parts) or "The planner could not produce an answer."


async def synthesizer_node(state: TripState) -> dict:
    payload = {
        "user_query": state["user_query"],
        "parsed": state.get("parsed"),
        "destination": state.get("destination_result"),
        "itinerary": state.get("itinerary_result"),
        "budget": state.get("budget_result"),
        "errors": [
            item for item in (state.get("errors") or []) if item.get("agent") != "synthesizer"
        ],
        "contributed": [name for name in (state.get("route") or []) if state.get(f"{name}_result")],
    }
    try:
        answer = await ainvoke_text(
            [SystemMessage(content=SYNTH_SYSTEM), HumanMessage(content=json.dumps(payload, indent=2))],
            temperature=0.2,
        )
        if not answer:
            raise ValueError("Empty synthesizer response")
    except Exception as exc:  # noqa: BLE001
        return {
            "final_answer": _fallback_answer(state),
            "errors": append_error(state, "synthesizer", str(exc)),
            "agent_trace": append_trace(
                state,
                {
                    "agent": "synthesizer",
                    "status": "error",
                    "summary": "Used templated fallback",
                    "error": str(exc),
                },
            ),
        }
    return {
        "final_answer": answer,
        "agent_trace": append_trace(
            state,
            {"agent": "synthesizer", "status": "ok", "summary": "Composed traveller-facing answer"},
        ),
    }
