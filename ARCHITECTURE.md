# Production architecture on Azure

Five hundred concurrent users planning trips is an LLM-duration problem, not a page-serve problem. A run is several sequential model calls and can last tens of seconds. I would not pin that work to the HTTP process that serves the SPA.

**Provision.** One resource group, Bicep or Terraform. Azure Container Apps for two workloads: a public API/UI (FastAPI serving the Vite build) and a worker that runs LangGraph. Azure Front Door in front. Azure Database for PostgreSQL Flexible Server for `requests` / `agent_runs` (the SQLite models already swap with `DATABASE_URL`). Redis for job status and SSE fan-out. Secrets in Key Vault, injected via the apps’ managed identity. Model access through Azure OpenAI or OpenRouter as a vault secret, never in the image.

**Scale.** The API scales on HTTP concurrency and returns 202 + job id when the graph starts. Runs enqueue on Azure Service Bus; workers scale on queue depth. That caps in-flight LLM spend instead of holding hundreds of long SSE sockets on one replica. Per-user rate limits by Entra object id. Postgres timescales the audit tables, not the inference path.

**Auth.** Microsoft Entra ID. SPA: MSAL. API: JWT. App roles `Traveller` and `Operator` replace today’s query-param stub. Only Operator can list traces and metrics. Deny anonymous graph execution.

**Monitor.** Application Insights and OpenTelemetry: request id, node, model, tokens, latency, error. Alerts on p95 duration, LLM 5xx, queue age, and guardrail failures (over-budget, constraint drops). Log Analytics for ops; `agent_runs` remains the system of record for “which agent handled this.”
