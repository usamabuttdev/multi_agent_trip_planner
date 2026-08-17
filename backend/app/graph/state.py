from typing import Any, Optional, TypedDict


class AgentError(TypedDict):
    agent: str
    error: str


class TraceStep(TypedDict, total=False):
    agent: str
    status: str
    summary: str
    error: Optional[str]


class TripState(TypedDict, total=False):
    request_id: str
    user_query: str
    parsed: Optional[dict[str, Any]]
    route: list[str]
    destination_result: Optional[dict[str, Any]]
    itinerary_result: Optional[dict[str, Any]]
    budget_result: Optional[dict[str, Any]]
    agent_trace: list[TraceStep]
    errors: list[AgentError]
    final_answer: Optional[str]
    contributing_agents: list[str]
