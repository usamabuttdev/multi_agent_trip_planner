from __future__ import annotations

from functools import lru_cache
from typing import Literal

from langgraph.graph import END, START, StateGraph

from app.graph.budget import budget_node
from app.graph.destination import destination_node
from app.graph.itinerary import itinerary_node
from app.graph.planner import planner_node
from app.graph.state import TripState
from app.graph.synthesizer import synthesizer_node

NextHop = Literal["destination", "itinerary", "budget", "synthesizer"]
_ORDER: list[NextHop] = ["destination", "itinerary", "budget", "synthesizer"]


def _route(state: TripState) -> list[str]:
    return list(state.get("route") or [])


def after_planner(state: TripState) -> NextHop:
    return _next_needed(state, after=None)


def after_destination(state: TripState) -> NextHop:
    return _next_needed(state, after="destination")


def after_itinerary(state: TripState) -> NextHop:
    return _next_needed(state, after="itinerary")


def _next_needed(state: TripState, after: str | None) -> NextHop:
    route = _route(state)
    start = 0 if after is None else _ORDER.index(after) + 1  # type: ignore[arg-type]
    for name in _ORDER[start:]:
        if name == "synthesizer" or name in route:
            return name
    return "synthesizer"


@lru_cache
def get_graph():
    workflow = StateGraph(TripState)
    workflow.add_node("planner", planner_node)
    workflow.add_node("destination", destination_node)
    workflow.add_node("itinerary", itinerary_node)
    workflow.add_node("budget", budget_node)
    workflow.add_node("synthesizer", synthesizer_node)

    workflow.add_edge(START, "planner")
    workflow.add_conditional_edges(
        "planner",
        after_planner,
        {
            "destination": "destination",
            "itinerary": "itinerary",
            "budget": "budget",
            "synthesizer": "synthesizer",
        },
    )
    workflow.add_conditional_edges(
        "destination",
        after_destination,
        {
            "itinerary": "itinerary",
            "budget": "budget",
            "synthesizer": "synthesizer",
        },
    )
    workflow.add_conditional_edges(
        "itinerary",
        after_itinerary,
        {"budget": "budget", "synthesizer": "synthesizer"},
    )
    workflow.add_edge("budget", "synthesizer")
    workflow.add_edge("synthesizer", END)
    return workflow.compile()
