type ApiFetchOptions = RequestInit & { accessToken?: string }

/** Like fetch(), with the API base, optional bearer token and HTTP error checking. */
export async function apiFetch(path: string, options: ApiFetchOptions = {}): Promise<Response> {
  if (!path.startsWith('/') || path.startsWith('//') || path.includes('\\')) {
    throw new Error('Use an API path starting with a single slash.')
  }
  const baseUrl = import.meta.env?.VITE_API_BASE_URL || '/api/v1'
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
  if (!response.ok) throw new Error(`Request failed (HTTP ${response.status}).`)
  return response
}
