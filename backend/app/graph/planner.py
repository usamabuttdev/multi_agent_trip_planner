from __future__ import annotations

from langchain_core.messages import HumanMessage, SystemMessage

from app.graph.llm import ainvoke_structured
from app.graph.state import TripState
from app.graph.tracing import append_error, append_trace, mark_contributed
from app.models.contracts import AgentName, PlannerOutput

PLANNER_SYSTEM = """You are the orchestration planner for a trip-planning platform.

Extract slots from the user's request and decide the MINIMUM specialist agents to run.

Agents:
- destination: suggest places. Include when the user has not named a specific city/town, or asks for alternatives.
- itinerary: day-by-day plan. Include when they want a trip, days, or what to do there.
- budget: cost the plan vs a cap. Include when they mention money, a budget, cheap/expensive, or "under X".

Rules:
- If they already named a specific destination to plan (e.g. "3 days in Lisbon"), do NOT include destination unless they also ask for other places.
- If itinerary is needed and no specific destination is named, destination MUST run first.
- Full briefs like "5 days somewhere warm in Europe under 1500 pounds" need all three, in order destination → itinerary → budget.
- Compare/suggest-only queries need destination only.
- Cost-check of an existing plan needs budget only (and itinerary if they asked to rebuild the days).
- Hard constraints are must-not-violate items (not Spain, under 1500, no flying). Preferences are soft.

Return structured fields only. Keep reasoning to one or two sentences.
"""

VALID_ORDER: list[AgentName] = ["destination", "itinerary", "budget"]


def normalize_route(parsed: PlannerOutput, user_query: str) -> list[AgentName]:
    agents: list[AgentName] = []
    for name in parsed.agents:
        if name in VALID_ORDER and name not in agents:
            agents.append(name)

    query = user_query.lower()
    wants_suggestions = any(
        word in query for word in ("somewhere", "anywhere", "suggest", "ideas", "alternatives", "recommend")
    )
    if parsed.named_destination and "destination" in agents and not wants_suggestions:
        agents = [name for name in agents if name != "destination"]

    if "itinerary" in agents and not parsed.named_destination and "destination" not in agents:
        agents.insert(0, "destination")

    if not agents:
        if parsed.named_destination:
            agents = ["itinerary"]
        else:
            agents = ["destination", "itinerary"]
        if parsed.budget_amount is not None:
            agents.append("budget")

    chosen = set(agents)
    return [name for name in VALID_ORDER if name in chosen]


async def planner_node(state: TripState) -> dict:
    query = state["user_query"]
    try:
        parsed = await ainvoke_structured(
            PlannerOutput,
            [SystemMessage(content=PLANNER_SYSTEM), HumanMessage(content=query)],
            temperature=0.1,
        )
        route = normalize_route(parsed, query)
        dumped = parsed.model_dump()
        dumped["agents"] = route
        return {
            "parsed": dumped,
            "route": route,
            "agent_trace": append_trace(
                state,
                {
                    "agent": "planner",
                    "status": "ok",
                    "summary": parsed.reasoning or f"Route: {', '.join(route)}",
                },
            ),
            "contributing_agents": mark_contributed(state, "planner"),
        }
    except Exception as exc:  # noqa: BLE001 — node must never crash the graph
        fallback: list[AgentName] = ["destination", "itinerary", "budget"]
        parsed = PlannerOutput(
            agents=fallback,
            reasoning="Planner failed; defaulting to the full specialist chain.",
            missing_slots=["planner_error"],
        )
        return {
            "parsed": parsed.model_dump(),
            "route": fallback,
            "errors": append_error(state, "planner", str(exc)),
            "agent_trace": append_trace(
                state,
                {"agent": "planner", "status": "error", "summary": "Fell back to full chain", "error": str(exc)},
            ),
            "contributing_agents": mark_contributed(state, "planner"),
        }
