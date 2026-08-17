from __future__ import annotations

import json

from langchain_core.messages import HumanMessage, SystemMessage

from app.graph.guardrails import apply_budget_guardrails, budget_needs_retry
from app.graph.llm import ainvoke_structured
from app.graph.state import TripState
from app.graph.tracing import append_error, append_trace, parsed_dict
from app.models.contracts import BudgetOutput, PlannerOutput

BUDGET_SYSTEM = """You are the Budget Agent for a trip-planning platform.

Estimate a realistic total for the proposed trip in the user's currency, as a sum of line items
(flights or intercity travel, lodging, food, local transport, activities, buffer).

Hard rules:
- NEVER silently exceed the user's budget.
- If the estimate is over the cap: set within_budget=false, set overage, AND propose a cheaper_alternative
  with a new estimated_total that is at or under the cap, plus concrete changes (not vague "spend less").
- If under the cap: within_budget=true, overage=0, cheaper_alternative=null.
- Costs are estimates from general knowledge, not live quotes. Say so in caveats.
- Include the user's budget as user_budget when known.
- Line items should add up to total (or within a pound).
"""

RETRY_SYSTEM = (
    BUDGET_SYSTEM
    + "\nYour previous estimate exceeded the budget without a cheaper_alternative. "
    "You MUST return a cheaper_alternative whose estimated_total is <= user_budget."
)


async def _invoke_budget(payload: dict, system: str) -> BudgetOutput:
    result = await ainvoke_structured(
        BudgetOutput,
        [SystemMessage(content=system), HumanMessage(content=json.dumps(payload, indent=2))],
        temperature=0.2,
    )
    assert isinstance(result, BudgetOutput)
    return result


async def budget_node(state: TripState) -> dict:
    parsed = PlannerOutput.model_validate(parsed_dict(state))
    payload = {
        "user_query": state["user_query"],
        "parsed": parsed.model_dump(),
        "destination_result": state.get("destination_result"),
        "itinerary_result": state.get("itinerary_result"),
    }
    try:
        result = await _invoke_budget(payload, BUDGET_SYSTEM)
        if budget_needs_retry(result):
            retry_payload = {**payload, "previous_estimate": result.model_dump()}
            try:
                result = await _invoke_budget(retry_payload, RETRY_SYSTEM)
            except Exception:
                pass
        result = apply_budget_guardrails(result, parsed)
        over_note = (
            f"OVER by {result.overage} {result.currency}"
            if result.user_budget is not None and not result.within_budget
            else f"within {result.user_budget} {result.currency}" if result.user_budget is not None else "no cap"
        )
        return {
            "budget_result": result.model_dump(),
            "agent_trace": append_trace(
                state,
                {
                    "agent": "budget",
                    "status": "ok",
                    "summary": f"Total {result.total:.0f} {result.currency} ({over_note})",
                },
            ),
        }
    except Exception as exc:  # noqa: BLE001
        return {
            "budget_result": None,
            "errors": append_error(state, "budget", str(exc)),
            "agent_trace": append_trace(
                state,
                {"agent": "budget", "status": "error", "summary": "Budget agent failed", "error": str(exc)},
            ),
        }
