"""Programmatic guardrails. Prompt rules are advisory; these are the platform rules."""

from __future__ import annotations

import re

from app.models.contracts import (
    BudgetOutput,
    CheaperAlternative,
    DestinationOutput,
    ItineraryOutput,
    PlannerOutput,
    RejectedDestination,
)

_EXCLUDE_RE = re.compile(
    r"\b(?:not|no|except|excluding|avoid(?:ing)?)\s+([A-Za-z][A-Za-z\s-]{1,40})",
    re.IGNORECASE,
)


def _normalize(text: str) -> str:
    return re.sub(r"\s+", " ", text).strip().lower()


def extract_exclusions(parsed: PlannerOutput, user_query: str) -> list[str]:
    blobs = list(parsed.hard_constraints) + [user_query]
    found: list[str] = []
    for blob in blobs:
        if not blob:
            continue
        for match in _EXCLUDE_RE.finditer(blob):
            token = _normalize(match.group(1))
            token = re.sub(r"[.,;:!?]+$", "", token)
            token = re.sub(r"\b(please|thanks|city|cities|country|countries)\b", "", token).strip()
            if token and token not in found:
                found.append(token)
    return found


def _matches_exclusion(name: str, country: str, exclusions: list[str]) -> str | None:
    haystack = _normalize(f"{name} {country}")
    for exclusion in exclusions:
        if exclusion and exclusion in haystack:
            return exclusion
    return None


def apply_destination_guardrails(
    result: DestinationOutput,
    parsed: PlannerOutput,
    user_query: str,
) -> DestinationOutput:
    exclusions = extract_exclusions(parsed, user_query)
    kept = []
    rejected = list(result.rejected)

    for suggestion in result.suggestions:
        if not suggestion.constraint_check.passed:
            rejected.append(
                RejectedDestination(
                    name=suggestion.name,
                    reason=suggestion.constraint_check.notes or "Failed declared constraint check",
                )
            )
            continue
        hit = _matches_exclusion(suggestion.name, suggestion.country, exclusions)
        if hit:
            rejected.append(
                RejectedDestination(
                    name=suggestion.name,
                    reason=f"Hard constraint violation: user excluded '{hit}'",
                )
            )
            continue
        kept.append(suggestion)

    kept_names = {suggestion.name.lower(): suggestion.name for suggestion in kept}
    primary: str | None = None
    if result.primary and result.primary.lower() in kept_names:
        primary = kept_names[result.primary.lower()]
    elif kept:
        primary = kept[0].name

    notes = result.notes
    if not kept:
        extra = (
            "No destination survived hard-constraint checks. Relax a constraint to get suggestions."
        )
        notes = f"{notes} {extra}".strip() if notes else extra

    return result.model_copy(
        update={"suggestions": kept, "rejected": rejected, "primary": primary, "notes": notes}
    )


def apply_itinerary_guardrails(result: ItineraryOutput) -> ItineraryOutput:
    days = []
    for day in result.days:
        if (
            len(day.activities) >= 3
            and not (day.travel_notes or "").strip()
            and not (day.uncertainty or "").strip()
        ):
            day = day.model_copy(
                update={
                    "uncertainty": (
                        "Multiple activities in one day without travel notes; "
                        "sequencing and transfer times are uncertain."
                    )
                }
            )
        days.append(day)

    feasibility = result.feasibility_notes.strip()
    if not feasibility:
        feasibility = "Feasibility is based on typical tourist pacing, not live timetables."
    return result.model_copy(update={"days": days, "feasibility_notes": feasibility})


def budget_needs_retry(result: BudgetOutput) -> bool:
    cap = result.user_budget
    if cap is None:
        return False
    return result.total > cap and result.cheaper_alternative is None


def apply_budget_guardrails(result: BudgetOutput, parsed: PlannerOutput) -> BudgetOutput:
    cap = result.user_budget if result.user_budget is not None else parsed.budget_amount
    currency = result.currency or parsed.budget_currency or "GBP"
    total = result.total
    if result.line_items:
        items_sum = round(sum(item.amount for item in result.line_items), 2)
        if abs(items_sum - total) > 1:
            total = items_sum

    alternative = result.cheaper_alternative
    if cap is None:
        within = True
        overage = None
        alternative = None
    else:
        within = total <= cap + 0.009
        overage = 0.0 if within else round(total - cap, 2)
        if within:
            alternative = None
        elif alternative is None:
            alternative = CheaperAlternative(
                summary="Trim paid extras and shift to cheaper lodging to stay under the cap.",
                estimated_total=round(cap * 0.92, 2),
                changes=[
                    "Switch to mid-range lodging or an outer neighbourhood",
                    "Replace one paid day-trip with a free walking route",
                    "Cook breakfasts instead of cafes every morning",
                ],
            )

    return result.model_copy(
        update={
            "currency": currency,
            "total": total,
            "user_budget": cap,
            "within_budget": within,
            "overage": overage,
            "cheaper_alternative": alternative,
        }
    )
