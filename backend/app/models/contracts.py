from typing import Literal, Optional

from pydantic import BaseModel, Field


AgentName = Literal["destination", "itinerary", "budget"]


class PlannerOutput(BaseModel):
    duration_days: Optional[int] = Field(None, description="Trip length in days, if stated or implied")
    budget_amount: Optional[float] = Field(None, description="Numeric budget cap")
    budget_currency: Optional[str] = Field(None, description="ISO-like code: GBP, EUR, USD")
    climate: Optional[str] = None
    region: Optional[str] = None
    interests: list[str] = Field(default_factory=list)
    named_destination: Optional[str] = Field(
        None, description="Specific city or place the user already chose, else null"
    )
    hard_constraints: list[str] = Field(
        default_factory=list,
        description="Must-not-violate constraints, e.g. 'not Spain', 'under 1500 GBP', 'no flying'",
    )
    preferences: list[str] = Field(default_factory=list, description="Soft preferences")
    agents: list[AgentName] = Field(
        default_factory=list,
        description="Which specialist agents to run, in dependency order",
    )
    missing_slots: list[str] = Field(default_factory=list)
    reasoning: str = Field("", description="Short justification for the chosen route")


class ConstraintCheck(BaseModel):
    passed: bool
    notes: str


class DestinationSuggestion(BaseModel):
    name: str
    country: str
    why_it_fits: list[str] = Field(
        default_factory=list,
        description="Each item maps a stated preference to why this place satisfies it",
    )
    constraint_check: ConstraintCheck
    typical_daily_cost_band: str


class RejectedDestination(BaseModel):
    name: str
    reason: str


class DestinationOutput(BaseModel):
    suggestions: list[DestinationSuggestion] = Field(default_factory=list)
    primary: Optional[str] = Field(None, description="Chosen city for downstream itinerary")
    rejected: list[RejectedDestination] = Field(default_factory=list)
    notes: str = ""


class DayPlan(BaseModel):
    day: int
    title: str
    activities: list[str] = Field(default_factory=list)
    travel_notes: Optional[str] = None
    uncertainty: Optional[str] = None


class ItineraryOutput(BaseModel):
    destination: str
    days: list[DayPlan] = Field(default_factory=list)
    feasibility_notes: str
    consulted_destination_agent: bool = False


class BudgetLineItem(BaseModel):
    name: str
    amount: float
    notes: str = ""


class CheaperAlternative(BaseModel):
    summary: str
    estimated_total: float
    changes: list[str] = Field(default_factory=list)


class BudgetOutput(BaseModel):
    currency: str
    line_items: list[BudgetLineItem] = Field(default_factory=list)
    total: float
    user_budget: Optional[float] = None
    within_budget: bool
    overage: Optional[float] = None
    cheaper_alternative: Optional[CheaperAlternative] = None
    caveats: str = ""


class SynthesizerOutput(BaseModel):
    answer: str = Field(..., description="Single coherent answer for the traveller")


class AgentTraceStep(BaseModel):
    agent: str
    status: str
    summary: str = ""
    error: Optional[str] = None


class TripCreateRequest(BaseModel):
    query: str = Field(..., min_length=3, max_length=4000)


class TripResponse(BaseModel):
    request_id: str
    answer: str
    agents: list[str]
    status: str
    parsed: Optional[PlannerOutput] = None
    destination: Optional[DestinationOutput] = None
    itinerary: Optional[ItineraryOutput] = None
    budget: Optional[BudgetOutput] = None
    trace: list[AgentTraceStep] = Field(default_factory=list)
    error: Optional[str] = None


class TripSummary(BaseModel):
    id: str
    created_at: str
    user_query: str
    agents: list[str]
    status: str
    duration_ms: Optional[int] = None
    error: Optional[str] = None


class TripDetail(TripResponse):
    user_query: str
    created_at: str
    duration_ms: Optional[int] = None
    agent_runs: list[dict] = Field(default_factory=list)
