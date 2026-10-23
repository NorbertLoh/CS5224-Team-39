type ApiFetchOptions = RequestInit & { accessToken?: string }
import { apiBaseUrl } from './backend-config'

export class ApiError extends Error {
  constructor(public status: number, public code?: string) { super(`Request failed (HTTP ${status}).`) }
}

/** Like fetch(), with the API base, optional bearer token and HTTP error checking. */
export async function apiFetch(path: string, options: ApiFetchOptions = {}): Promise<Response> {
  if (!path.startsWith('/') || path.startsWith('//') || path.includes('\\')) {
    throw new Error('Use an API path starting with a single slash.')
  }
  const baseUrl = apiBaseUrl()
  const { accessToken, ...init } = options
  const headers = new Headers(init.headers)
  headers.set('Accept', 'application/json')
  if (accessToken) headers.set('Authorization', `Bearer ${accessToken}`)

  const response = await fetch(`${baseUrl.replace(/\/+$/, '')}${path}`, {
    ...init,
    headers,
    credentials: 'omit',
    cache: 'no-store',
    redirect: 'error',
  })
  if (!response.ok) {
    let code: string | undefined
    try {
      const body: { error?: { code?: unknown } } = await response.json()
      if (typeof body?.error?.code === 'string') code = body.error.code
    } catch {
      // Non-JSON failures retain the HTTP status without exposing raw response text.
    }
    throw new ApiError(response.status, code)
  }
  return response
}
