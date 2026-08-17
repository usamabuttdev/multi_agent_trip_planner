from __future__ import annotations

import json

from langchain_core.messages import HumanMessage, SystemMessage

from app.graph.guardrails import apply_destination_guardrails
from app.graph.llm import ainvoke_structured
from app.graph.state import TripState
from app.graph.tracing import append_error, append_trace, parsed_dict
from app.models.contracts import DestinationOutput, PlannerOutput

DESTINATION_SYSTEM = """You are the Destination Agent for a trip-planning platform.

Suggest 2-3 destinations that fit the user's stated climate, region, interests, duration, and budget band.

Hard rules:
- Justify EACH suggestion against stated preferences in why_it_fits (one bullet per preference it satisfies).
- Never recommend a place that breaks a hard constraint (exclusions, region, budget band if obviously impossible).
- If you considered a place and rejected it, put it in rejected with the reason.
- Set constraint_check.passed=false rather than listing a violating place in suggestions.
- Pick a single primary city for a downstream itinerary (the best overall fit, not a country).
- Typical daily cost bands should be honest (e.g. "£70-110 / person / day excl. flights").
- Use the user's currency when known.
"""


async def destination_node(state: TripState) -> dict:
    query = state["user_query"]
    parsed = PlannerOutput.model_validate(parsed_dict(state))
    payload = {
        "user_query": query,
        "parsed": parsed.model_dump(),
    }
    try:
        result = await ainvoke_structured(
            DestinationOutput,
            [
                SystemMessage(content=DESTINATION_SYSTEM),
                HumanMessage(content=json.dumps(payload, indent=2)),
            ],
            temperature=0.4,
        )
        result = apply_destination_guardrails(result, parsed, query)
        return {
            "destination_result": result.model_dump(),
            "agent_trace": append_trace(
                state,
                {
                    "agent": "destination",
                    "status": "ok",
                    "summary": (
                        f"Primary: {result.primary} "
                        f"({len(result.suggestions)} kept, {len(result.rejected)} rejected)"
                        if result.primary
                        else (result.notes or "No valid destinations")
                    ),
                },
            ),
        }
    except Exception as exc:  # noqa: BLE001
        return {
            "destination_result": None,
            "errors": append_error(state, "destination", str(exc)),
            "agent_trace": append_trace(
                state,
                {"agent": "destination", "status": "error", "summary": "Destination agent failed", "error": str(exc)},
            ),
        }
