# Notes — decisions, limits, what next

This is the walkthrough document for the take-home. The product is a small orchestrator, not a travel agency.

## What I chose and why

**Planner-then-execute DAG, not a supervisor loop.** A supervisor that "decides the next agent" looks more agentic and is harder to audit: it can loop, double-call, and spend unbounded tokens. A planner emits a route (`destination → itinerary → budget`, or a subset) and LangGraph executes that route with conditional edges. Bounded cost, deterministic chaining, easy to explain in an incident review.

**Structured output plus Python guardrails.** Prompt constraints are advisory. Destination suggestions that fail `constraint_check` or match an explicit exclusion (`not Spain`) are stripped before they become `primary`. Budget totals that exceed the cap cannot stay `within_budget=true`; if the model omits a cheaper alternative, the platform injects one after a single retry. That is the "internal AI platform" stance: the model proposes, the service enforces.

**Itinerary consults Destination through graph state**, not a nested tool call. Nested tools hide the chain from the audit log. Passing `destination_result.primary` on the state makes the dependency explicit.

**SQLite with a real schema.** `requests` + `agent_runs` is the audit trail an internal platform actually needs. SQLAlchemy so `DATABASE_URL` can later point at Postgres without rewriting models. On Render's free disk the file is ephemeral; that is called out rather than papered over.

**OpenRouter.** One key, many models. Default is `openrouter/free` so the demo stays on the free tier; set `OPENROUTER_MODEL` if you want a specific slug. The LLM client is one function (`get_llm`).

**Agent activity over token streaming.** Reviewers care which specialist is running. SSE emits node start/finish events; the UI renders chips. Cheaper than token streaming and more aligned with the brief's transparency requirement.

**One process can serve UI + API.** FastAPI mounts the Vite `dist` when present. That is what the current ngrok demo runs. Split Vercel+Render remains available; I did not have logged-in Vercel/Render accounts in this environment, so the live URL is an ngrok tunnel in front of that combined process.

## Honest limits

- Prices and opening hours are the model's general knowledge, not live quotes.
- SQLite on a free Render instance does not survive deploys or idle shutdowns.
- No eval harness. The three smoke prompts (full brief, named city, exclusion) are the current bar.
- Planner fallback on failure is "run all three agents". Safe, not always cheapest.
- CORS defaults to `*` for a frictionless deploy. I would lock this to the Vercel origin in a real environment.
- The previous public URL was ngrok, not Render. It dies if the local process stops. Next hosting step: Docker on Render with `OPENROUTER_API_KEY` set.

## If I had another afternoon, in order

1. Neon/Postgres so the audit log survives deploys.
2. A fixture eval of ~8 prompts: constraint violation, over-budget, named city, vague query, budget-only, destination-only, agent timeout, unparseable slots.
3. Lock CORS to the frontend origin and add a request-id on every log line.
4. Cache destination suggestions for identical parses (cost control).
5. Proper identity only if the live round requires it — the `?role=operator` stub is intentionally not auth.
