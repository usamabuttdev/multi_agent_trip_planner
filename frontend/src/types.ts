export type AgentName = 'planner' | 'destination' | 'itinerary' | 'budget' | 'synthesizer'

export interface AgentTraceStep {
  agent: string
  status: string
  summary?: string
  error?: string | null
}

export interface ConstraintCheck {
  passed: boolean
  notes: string
}

export interface DestinationSuggestion {
  name: string
  country: string
  why_it_fits: string[]
  constraint_check: ConstraintCheck
  typical_daily_cost_band: string
}

export interface RejectedDestination {
  name: string
  reason: string
}

export interface DestinationOutput {
  suggestions: DestinationSuggestion[]
  primary: string | null
  rejected: RejectedDestination[]
  notes: string
}

export interface DayPlan {
  day: number
  title: string
  activities: string[]
  travel_notes: string | null
  uncertainty: string | null
}

export interface ItineraryOutput {
  destination: string
  days: DayPlan[]
  feasibility_notes: string
  consulted_destination_agent: boolean
}

export interface BudgetLineItem {
  name: string
  amount: number
  notes: string
}

export interface CheaperAlternative {
  summary: string
  estimated_total: number
  changes: string[]
}

export interface BudgetOutput {
  currency: string
  line_items: BudgetLineItem[]
  total: number
  user_budget: number | null
  within_budget: boolean
  overage: number | null
  cheaper_alternative: CheaperAlternative | null
  caveats: string
}

export interface PlannerOutput {
  duration_days: number | null
  budget_amount: number | null
  budget_currency: string | null
  climate: string | null
  region: string | null
  interests: string[]
  named_destination: string | null
  hard_constraints: string[]
  preferences: string[]
  agents: string[]
  missing_slots: string[]
  reasoning: string
}

export interface TripResponse {
  request_id: string
  answer: string
  agents: string[]
  status: string
  parsed: PlannerOutput | null
  destination: DestinationOutput | null
  itinerary: ItineraryOutput | null
  budget: BudgetOutput | null
  trace: AgentTraceStep[]
  error: string | null
}

export interface TripSummary {
  id: string
  created_at: string
  user_query: string
  agents: string[]
  status: string
  duration_ms: number | null
  error: string | null
}

export interface Metrics {
  requests: number
  by_status: Record<string, number>
  agent_runs: Record<string, number>
  agent_errors: number
}

export interface AgentEvent {
  agent: string
  status: string
  summary?: string
  error?: string | null
}
