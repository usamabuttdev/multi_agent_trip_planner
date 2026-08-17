/**
 * Frontend env — same idea as backend/app/config.py.
 *
 * Local:  copy frontend/.env.example → frontend/.env and set VITE_API_URL
 * Vercel: Project → Settings → Environment Variables → VITE_API_URL, then Redeploy
 *
 * Value = public FastAPI origin, no trailing slash, e.g. https://your-api.vercel.app
 * Leave empty for local Vite (proxies /api to http://127.0.0.1:8000).
 */
function readBackendUrl(): string {
  const raw = import.meta.env.VITE_API_URL ?? import.meta.env.VITE_BACKEND_URL ?? ''
  if (typeof raw !== 'string') return ''
  return raw.trim().replace(/\/$/, '')
}

export const backendUrl = readBackendUrl()
