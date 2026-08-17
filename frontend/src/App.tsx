import { type FormEvent, useEffect, useMemo, useState } from 'react'
import Markdown from 'react-markdown'
import { fetchHealth, fetchMetrics, fetchTrip, fetchTrips, planTripStream } from './api'
import { backendUrl } from './config'
import type { AgentEvent, Metrics, TripResponse, TripSummary } from './types'

const EXAMPLES = [
  'Five day trip somewhere warm in Europe for under 1500 pounds',
  '3 days in Lisbon under 800 euros',
  'Somewhere warm in Europe, not Spain, around a week, interested in food and walking',
]

const SPECIALISTS = ['destination', 'itinerary', 'budget'] as const

function isOperatorRole(): boolean {
  return new URLSearchParams(window.location.search).get('role') === 'operator'
}

function money(amount: number, currency: string): string {
  try {
    return new Intl.NumberFormat('en-GB', { style: 'currency', currency }).format(amount)
  } catch {
    return `${amount} ${currency}`
  }
}

export default function App() {
  const operator = useMemo(isOperatorRole, [])
  const [query, setQuery] = useState(EXAMPLES[0])
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [result, setResult] = useState<TripResponse | null>(null)
  const [activity, setActivity] = useState<AgentEvent[]>([])
  const [history, setHistory] = useState<TripSummary[]>([])
  const [metrics, setMetrics] = useState<Metrics | null>(null)
  const [llmReady, setLlmReady] = useState<boolean | null>(null)

  async function refreshSidebar() {
    try {
      const [trips, stats, health] = await Promise.all([
        fetchTrips(),
        fetchMetrics(),
        fetchHealth(),
      ])
      setHistory(trips)
      setMetrics(stats)
      setLlmReady(health.llm_configured)
    } catch {
      /* API may be down on first paint */
    }
  }

  useEffect(() => {
    void refreshSidebar()
  }, [])

  async function openTrip(item: TripSummary) {
    setQuery(item.user_query)
    setError(null)
    setLoading(false)
    try {
      const detail = await fetchTrip(item.id)
      setResult(detail)
      setActivity(
        (detail.trace ?? []).map((step) => ({
          agent: step.agent,
          status: step.status,
          summary: step.summary,
          error: step.error,
        })),
      )
    } catch (err) {
      setResult(null)
      setError(err instanceof Error ? err.message : 'Could not load that request')
    }
  }

  async function onSubmit(event: FormEvent) {
    event.preventDefault()
    setLoading(true)
    setError(null)
    setResult(null)
    setActivity([])
    try {
      const trip = await planTripStream(query, (event) => {
        setActivity((current) => [...current.filter((item) => item.agent !== event.agent), event])
      })
      setResult(trip)
      await refreshSidebar()
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Request failed')
    } finally {
      setLoading(false)
    }
  }

  return (
    <div className="page">
      <header className="hero">
        <p className="eyebrow">Internal trip orchestrator</p>
        <h1>Plan a trip. Watch the agents.</h1>
        <p className="lede">
          Destination, Itinerary, and Budget are separate specialists. A planner routes the request
          and a synthesizer writes one answer. {operator ? 'Operator audit view.' : 'Traveller view.'}
        </p>
        <p className="muted">
          API: {backendUrl || 'local Vite proxy → http://127.0.0.1:8000'}
        </p>
        {llmReady === false && (
          <p className="banner">Backend is up, but OPENROUTER_API_KEY is missing.</p>
        )}
      </header>

      <form className="panel" onSubmit={onSubmit}>
        <label htmlFor="query">What do you want?</label>
        <textarea
          id="query"
          rows={4}
          value={query}
          onChange={(event) => setQuery(event.target.value)}
          disabled={loading}
        />
        <div className="examples">
          {EXAMPLES.map((example) => (
            <button
              key={example}
              type="button"
              className="chip"
              onClick={() => setQuery(example)}
              disabled={loading}
            >
              {example}
            </button>
          ))}
        </div>
        <button className="primary" type="submit" disabled={loading || query.trim().length < 3}>
          {loading ? 'Running agents…' : 'Plan trip'}
        </button>
      </form>

      {(loading || activity.length > 0) && (
        <section className="panel">
          <h2>Agent activity</h2>
          <ol className="activity">
            {['planner', ...SPECIALISTS, 'synthesizer'].map((name) => {
              const event = activity.find((item) => item.agent === name)
              const status = event?.status ?? (loading ? 'waiting' : 'idle')
              return (
                <li key={name} className={status}>
                  <strong>{name}</strong>
                  <span>{event?.error || event?.summary || status}</span>
                </li>
              )
            })}
          </ol>
        </section>
      )}

      {error && <p className="banner error">{error}</p>}

      {result && (
        <section className="panel result">
          <div className="meta">
            <span>Status: {result.status}</span>
            <span>Agents: {result.agents.length ? result.agents.join(', ') : 'none'}</span>
            {result.request_id && <span>id: {result.request_id}</span>}
          </div>
          {result.error && (
            <p className="warn">
              Failure: {result.error}
            </p>
          )}
          <h2>Answer</h2>
          {result.answer ? (
            <div className="answer">
              <Markdown>{result.answer}</Markdown>
            </div>
          ) : (
            <p className="answer">No synthesised answer was stored.</p>
          )}

          {result.trace.length > 0 && (
            <article>
              <h3>Agent trace</h3>
              <ol className="activity">
                {result.trace.map((step, index) => (
                  <li key={`${step.agent}-${index}`} className={step.status}>
                    <strong>
                      {step.agent} · {step.status}
                    </strong>
                    <span>{step.error || step.summary || '—'}</span>
                  </li>
                ))}
              </ol>
            </article>
          )}

          {result.destination && (
            <article>
              <h3>Destination agent</h3>
              {result.destination.primary && <p>Primary: {result.destination.primary}</p>}
              <ul>
                {result.destination.suggestions.map((item) => (
                  <li key={item.name}>
                    <strong>
                      {item.name}, {item.country}
                    </strong>
                    <div>{item.why_it_fits.join(' · ')}</div>
                    <div className="muted">{item.typical_daily_cost_band}</div>
                  </li>
                ))}
              </ul>
              {result.destination.rejected.length > 0 && (
                <p className="muted">
                  Rejected: {result.destination.rejected.map((item) => `${item.name} (${item.reason})`).join('; ')}
                </p>
              )}
            </article>
          )}

          {result.itinerary && (
            <article>
              <h3>Itinerary agent{result.itinerary.consulted_destination_agent ? ' · consulted Destination' : ''}</h3>
              <p>{result.itinerary.feasibility_notes}</p>
              <ol>
                {result.itinerary.days.map((day) => (
                  <li key={day.day}>
                    <strong>
                      Day {day.day}: {day.title}
                    </strong>
                    <div>{day.activities.join(' · ')}</div>
                    {day.travel_notes && <div className="muted">Travel: {day.travel_notes}</div>}
                    {day.uncertainty && <div className="warn">Uncertain: {day.uncertainty}</div>}
                  </li>
                ))}
              </ol>
            </article>
          )}

          {result.budget && (
            <article>
              <h3>Budget agent</h3>
              <p>
                Total {money(result.budget.total, result.budget.currency)}
                {result.budget.user_budget != null && (
                  <> vs cap {money(result.budget.user_budget, result.budget.currency)}</>
                )}
                {' — '}
                {result.budget.within_budget ? 'within budget' : `over by ${result.budget.overage}`}
              </p>
              <ul>
                {result.budget.line_items.map((item) => (
                  <li key={item.name}>
                    {item.name}: {money(item.amount, result.budget!.currency)} {item.notes && `· ${item.notes}`}
                  </li>
                ))}
              </ul>
              {result.budget.cheaper_alternative && (
                <p>
                  Cheaper alternative ({money(result.budget.cheaper_alternative.estimated_total, result.budget.currency)}
                  ): {result.budget.cheaper_alternative.summary}.{' '}
                  {result.budget.cheaper_alternative.changes.join('; ')}
                </p>
              )}
              {result.budget.caveats && <p className="muted">{result.budget.caveats}</p>}
            </article>
          )}
        </section>
      )}

      <aside className="panel">
        <h2>{operator ? 'Audit log' : 'Recent requests'}</h2>
        {operator && metrics && (
          <p className="muted">
            {metrics.requests} requests · {metrics.agent_errors} agent errors
          </p>
        )}
        {history.length === 0 && <p className="muted">No requests yet.</p>}
        <ul className="history">
          {history.map((item) => (
            <li key={item.id}>
              <button type="button" onClick={() => void openTrip(item)}>
                {item.user_query}
              </button>
              <span className="muted">
                {item.agents.join(', ') || 'no specialists'} · {item.status}
                {item.duration_ms != null ? ` · ${item.duration_ms}ms` : ''}
              </span>
              {item.error && <span className="warn">{item.error}</span>}
            </li>
          ))}
        </ul>
        {!operator && (
          <p className="muted">
            Operator stub: add <code>?role=operator</code> to the URL for a slightly denser audit view.
          </p>
        )}
      </aside>
    </div>
  )
}
