from __future__ import annotations

import json

from langchain_core.messages import HumanMessage, SystemMessage

from app.graph.guardrails import apply_itinerary_guardrails
from app.graph.llm import ainvoke_structured
from app.graph.state import TripState
from app.graph.tracing import append_error, append_trace, parsed_dict
from app.models.contracts import ItineraryOutput, PlannerOutput

ITINERARY_SYSTEM = """You are the Itinerary Agent for a trip-planning platform.

Build a realistic day-by-day plan for ONE destination and the given trip length.

Hard rules:
- Sequence activities so travel time is plausible (cluster neighbourhoods; do not ping-pong across a city or country).
- Each day: morning/afternoon/evening or a tight list of activities, plus travel_notes when moving between areas.
- If you are uncertain (opening hours, seasonal ferries, whether two sights fit), set that day's uncertainty instead of guessing confidently.
- Do not invent impossible same-day combinations (e.g. Rome and Venice in one day).
- If duration is missing, assume 4 days and say so in feasibility_notes.
- Pace: 2-4 activities per day, with meals implied not listed unless relevant.
- Set consulted_destination_agent true only if destination_result was provided.
"""


def _place_from_state(state: TripState, parsed: PlannerOutput) -> str | None:
    dest = state.get("destination_result") or {}
    primary = dest.get("primary") if dest else None
    if primary:
        return primary
    if dest.get("suggestions"):
        return dest["suggestions"][0].get("name")
    return parsed.named_destination


async def itinerary_node(state: TripState) -> dict:
    parsed = PlannerOutput.model_validate(parsed_dict(state))
    place = _place_from_state(state, parsed)
    if not place:
        return {
            "itinerary_result": None,
            "errors": append_error(state, "itinerary", "No destination available to plan"),
            "agent_trace": append_trace(
                state,
                {
                    "agent": "itinerary",
                    "status": "error",
                    "summary": "Skipped: no destination",
                    "error": "No destination available to plan",
                },
            ),
        }

    payload = {
        "user_query": state["user_query"],
        "parsed": parsed.model_dump(),
        "destination_result": state.get("destination_result"),
        "plan_for": place,
        "duration_days": parsed.duration_days or 4,
    }
    try:
        result = await ainvoke_structured(
            ItineraryOutput,
            [
                SystemMessage(content=ITINERARY_SYSTEM),
                HumanMessage(content=json.dumps(payload, indent=2)),
            ],
            temperature=0.4,
        )
        if state.get("destination_result"):
            result = result.model_copy(update={"consulted_destination_agent": True, "destination": place})
        else:
            result = result.model_copy(update={"destination": place})
        result = apply_itinerary_guardrails(result)
        return {
            "itinerary_result": result.model_dump(),
            "agent_trace": append_trace(
                state,
                {
                    "agent": "itinerary",
                    "status": "ok",
                    "summary": f"{len(result.days)}-day plan for {result.destination}",
                },
            ),
        }
    except Exception as exc:  # noqa: BLE001
        return {
            "itinerary_result": None,
            "errors": append_error(state, "itinerary", str(exc)),
            "agent_trace": append_trace(
                state,
                {"agent": "itinerary", "status": "error", "summary": "Itinerary agent failed", "error": str(exc)},
            ),
        }
