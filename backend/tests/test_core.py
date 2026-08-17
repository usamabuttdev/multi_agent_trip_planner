from __future__ import annotations

import json
import unittest

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.db import Base
from app.graph.llm import extract_json_object
from app.graph.guardrails import apply_budget_guardrails, apply_destination_guardrails
from app.graph.planner import normalize_route
from app.models.contracts import (
    BudgetLineItem,
    BudgetOutput,
    ConstraintCheck,
    DestinationOutput,
    DestinationSuggestion,
    PlannerOutput,
)
from app.models.tables import AgentRun, Request
from app.services.audit import create_request, finish_agent_run, finish_request, start_agent_run


class GuardrailTests(unittest.TestCase):
    def test_destination_drops_excluded_country(self) -> None:
        parsed = PlannerOutput(
            region="Europe",
            climate="warm",
            hard_constraints=["not Spain"],
            agents=["destination"],
        )
        raw = DestinationOutput(
            suggestions=[
                DestinationSuggestion(
                    name="Valencia",
                    country="Spain",
                    why_it_fits=["warm"],
                    constraint_check=ConstraintCheck(passed=True, notes="LLM missed the exclusion"),
                    typical_daily_cost_band="£80-110",
                ),
                DestinationSuggestion(
                    name="Lisbon",
                    country="Portugal",
                    why_it_fits=["warm", "budget"],
                    constraint_check=ConstraintCheck(passed=True, notes="fits"),
                    typical_daily_cost_band="£70-100",
                ),
            ],
            primary="Valencia",
            rejected=[],
        )
        cleaned = apply_destination_guardrails(raw, parsed, "somewhere warm in Europe, not Spain")
        names = [item.name for item in cleaned.suggestions]
        self.assertEqual(names, ["Lisbon"])
        self.assertEqual(cleaned.primary, "Lisbon")
        self.assertTrue(any("Spain" in item.reason or "spain" in item.reason.lower() for item in cleaned.rejected))

    def test_budget_never_silently_exceeds(self) -> None:
        parsed = PlannerOutput(budget_amount=1500, budget_currency="GBP", agents=["budget"])
        raw = BudgetOutput(
            currency="GBP",
            line_items=[
                BudgetLineItem(name="Flights", amount=600),
                BudgetLineItem(name="Stay", amount=800),
                BudgetLineItem(name="Food", amount=400),
            ],
            total=1800,
            user_budget=1500,
            within_budget=True,
            overage=None,
            cheaper_alternative=None,
        )
        cleaned = apply_budget_guardrails(raw, parsed)
        self.assertFalse(cleaned.within_budget)
        self.assertEqual(cleaned.overage, 300)
        self.assertIsNotNone(cleaned.cheaper_alternative)
        assert cleaned.cheaper_alternative is not None
        self.assertLessEqual(cleaned.cheaper_alternative.estimated_total, 1500)


class RouterTests(unittest.TestCase):
    def test_named_city_skips_destination(self) -> None:
        parsed = PlannerOutput(
            named_destination="Lisbon",
            duration_days=3,
            budget_amount=800,
            budget_currency="EUR",
            agents=["destination", "itinerary", "budget"],
        )
        route = normalize_route(parsed, "3 days in Lisbon under 800 euros")
        self.assertEqual(route, ["itinerary", "budget"])

    def test_open_brief_runs_full_chain(self) -> None:
        parsed = PlannerOutput(
            duration_days=5,
            budget_amount=1500,
            budget_currency="GBP",
            climate="warm",
            region="Europe",
            agents=["destination", "itinerary", "budget"],
        )
        route = normalize_route(parsed, "five day trip somewhere warm in Europe for under 1500 pounds")
        self.assertEqual(route, ["destination", "itinerary", "budget"])


class AuditTests(unittest.TestCase):
    def setUp(self) -> None:
        self.engine = create_engine("sqlite:///:memory:")
        Base.metadata.create_all(self.engine)
        self.Session = sessionmaker(bind=self.engine)

    def test_fake_run_writes_request_and_agent_rows(self) -> None:
        session = self.Session()
        request = create_request(session, "warm Europe under 1500")
        run = start_agent_run(session, request.id, "destination", json.dumps({"query": request.user_query}))
        finish_agent_run(session, run, status="ok", output_payload=json.dumps({"primary": "Lisbon"}))
        finish_request(
            session,
            request,
            status="completed",
            route_json=json.dumps(["destination"]),
            final_answer="Try Lisbon.",
            duration_ms=12,
        )
        stored = session.get(Request, request.id)
        assert stored is not None
        self.assertEqual(stored.status, "completed")
        runs = session.query(AgentRun).filter_by(request_id=request.id).all()
        self.assertEqual(len(runs), 1)
        self.assertEqual(runs[0].agent_name, "destination")
        self.assertEqual(runs[0].status, "ok")
        session.close()


class JsonExtractTests(unittest.TestCase):
    def test_plain_object(self) -> None:
        self.assertEqual(extract_json_object('{"a": 1}'), {"a": 1})

    def test_fenced_and_preamble(self) -> None:
        blob = 'User Safety: safe\n```json\n{"destination": "Lisbon", "days": []}\n```'
        self.assertEqual(extract_json_object(blob)["destination"], "Lisbon")

    def test_rejects_non_json(self) -> None:
        with self.assertRaises(ValueError):
            extract_json_object("User Safety: safe")


if __name__ == "__main__":
    unittest.main()
