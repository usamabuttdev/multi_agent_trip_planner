import type { AgentEvent, Metrics, TripResponse, TripSummary } from './types'
import { backendUrl } from './config'

const API_BASE = backendUrl

async function parseError(response: Response): Promise<string> {
  try {
    const body = await response.json()
    if (typeof body.detail === 'string') return body.detail
    return JSON.stringify(body.detail ?? body)
  } catch {
    return response.statusText
  }
}

export async function fetchHealth(): Promise<{ ok: boolean; llm_configured: boolean; model: string }> {
  const response = await fetch(`${API_BASE}/api/health`)
  if (!response.ok) throw new Error(await parseError(response))
  return response.json()
}

export async function fetchTrips(): Promise<TripSummary[]> {
  const response = await fetch(`${API_BASE}/api/trips`)
  if (!response.ok) throw new Error(await parseError(response))
  return response.json()
}

export async function fetchTrip(id: string): Promise<TripResponse> {
  const response = await fetch(`${API_BASE}/api/trips/${id}`)
  if (!response.ok) throw new Error(await parseError(response))
  return response.json()
}

export async function fetchMetrics(): Promise<Metrics> {
  const response = await fetch(`${API_BASE}/api/metrics`)
  if (!response.ok) throw new Error(await parseError(response))
  return response.json()
}

export async function planTripJson(query: string): Promise<TripResponse> {
  const response = await fetch(`${API_BASE}/api/trips`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ query }),
  })
  if (!response.ok) throw new Error(await parseError(response))
  return response.json()
}

export async function planTripStream(
  query: string,
  onAgent: (event: AgentEvent) => void,
): Promise<TripResponse> {
  const response = await fetch(`${API_BASE}/api/trips/stream`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json', Accept: 'text/event-stream' },
    body: JSON.stringify({ query }),
  })
  if (!response.ok) throw new Error(await parseError(response))
  if (!response.body) return planTripJson(query)

  const reader = response.body.getReader()
  const decoder = new TextDecoder()
  let buffer = ''
  let result: TripResponse | null = null

  while (true) {
    const { done, value } = await reader.read()
    if (done) break
    buffer += decoder.decode(value, { stream: true })
    const chunks = buffer.split('\n\n')
    buffer = chunks.pop() ?? ''
    for (const chunk of chunks) {
      const eventMatch = chunk.match(/^event:\s*(.+)$/m)
      const dataMatch = chunk.match(/^data:\s*(.+)$/m)
      if (!eventMatch || !dataMatch) continue
      const payload = JSON.parse(dataMatch[1]) as AgentEvent & TripResponse & { message?: string }
      if (eventMatch[1] === 'agent') onAgent(payload)
      if (eventMatch[1] === 'result') result = payload
      if (eventMatch[1] === 'error') throw new Error(payload.message || 'Orchestration failed')
    }
  }

  if (!result) throw new Error('Stream ended without a result')
  return result
}
