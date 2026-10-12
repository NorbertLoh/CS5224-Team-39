import type { ApiPath, ErrorDetail, ErrorEnvelope } from './api-types'

export type HttpMethod = 'GET' | 'POST' | 'PUT' | 'PATCH' | 'DELETE'
type QueryValue = string | number | boolean | null | undefined

export interface RequestOptions {
  method?: HttpMethod
  query?: Record<string, QueryValue>
  body?: unknown
  headers?: HeadersInit
  signal?: AbortSignal
}

export interface ApiClientOptions {
  baseUrl?: string
  getAccessToken?: () => string | null | Promise<string | null>
  fetch?: typeof globalThis.fetch
}

export class ApiError extends Error {
  readonly kind: 'http' | 'network' | 'invalid_response'
  readonly method: HttpMethod
  readonly status: number | undefined
  readonly code: string
  readonly requestId: string | undefined
  readonly details: ErrorDetail[]
  readonly retryAfterMs: number | undefined

  constructor(message: string, options: {
    kind: ApiError['kind']
    method: HttpMethod
    status?: number
    code: string
    requestId?: string
    details?: ErrorDetail[]
    retryAfterMs?: number
  }) {
    super(message)
    this.name = 'ApiError'
    this.kind = options.kind
    this.method = options.method
    this.status = options.status
    this.code = options.code
    this.requestId = options.requestId
    this.details = options.details ?? []
    this.retryAfterMs = options.retryAfterMs
  }
}

export function isAbortError(error: unknown): boolean {
  return error instanceof Error && error.name === 'AbortError'
}

function record(value: unknown): value is Record<string, unknown> {
  return typeof value === 'object' && value !== null
}

function requestId(value: unknown): string | undefined {
  return typeof value === 'string' && /^[A-Za-z0-9._-]{1,64}$/.test(value) ? value : undefined
}

function errorEnvelope(value: unknown): value is ErrorEnvelope {
  if (!record(value) || !record(value.error)) return false
  const error = value.error
  return typeof error.code === 'string' && /^[a-z][a-z0-9_]*$/.test(error.code)
    && typeof error.message === 'string' && error.message.length > 0
    && requestId(error.request_id) !== undefined && Array.isArray(error.details)
    && error.details.every(detail => record(detail)
      && typeof detail.field === 'string' && typeof detail.code === 'string'
      && typeof detail.message === 'string')
}

function retryAfter(value: string | null): number | undefined {
  if (!value) return undefined
  if (/^\d+$/.test(value)) {
    const ms = Number(value) * 1000
    return Number.isFinite(ms) ? ms : undefined
  }
  const date = Date.parse(value)
  return Number.isFinite(date) ? Math.max(0, date - Date.now()) : undefined
}

function safeHttpMessage(status: number): string {
  if (status === 401) return 'Please sign in again to continue.'
  if (status === 403) return 'You do not have permission to access this resource.'
  if (status === 404) return 'This resource could not be found.'
  if (status === 429) return 'Too many requests. Please try again later.'
  return 'The request could not be completed. Please try again.'
}

// Reject traversal and alternate origins before attaching any access token.
function safeSegments(path: string): boolean {
  try {
    return path.split('/').every(segment => {
      const decoded = decodeURIComponent(segment)
      return decoded !== '.' && decoded !== '..' && !/[\\/]/.test(decoded)
    })
  } catch {
    return false
  }
}

function normalizeBase(base: string): string {
  if (/[\\?#]/.test(base)) throw new Error('API base must have no query, fragment or backslash.')
  if (/^https?:\/\//.test(base)) {
    const url = new URL(base)
    if (url.username || url.password || !safeSegments(url.pathname)) {
      throw new Error('Invalid API base URL.')
    }
    return url.href.replace(/\/+$/, '')
  }
  if (!base.startsWith('/') || base.startsWith('//') || !safeSegments(base)) {
    throw new Error('API base must be an absolute HTTP(S) URL or an origin-relative path.')
  }
  return base.replace(/\/+$/, '')
}

export function createApiClient(options: ApiClientOptions = {}) {
  const base = normalizeBase(options.baseUrl ?? '/api/v1')
  const fetcher = options.fetch ?? globalThis.fetch.bind(globalThis)

  async function request<T = unknown>(path: ApiPath, optionsForRequest: RequestOptions = {}): Promise<T | undefined> {
    if (!/^\/(identity|tenant|scheduling|consultation|clinical-records|billing|document|fulfilment|notification)(\/|$)/.test(path)
      || /[\\?#]/.test(path) || !safeSegments(path)) {
      throw new Error('Use a service-relative API path and separate query parameters.')
    }
    const { method = 'GET', query, body, signal } = optionsForRequest
    if (method === 'GET' && body !== undefined) throw new Error('GET requests cannot have a body.')
    const search = new URLSearchParams()
    for (const [key, value] of Object.entries(query ?? {})) {
      if (value !== null && value !== undefined) search.set(key, String(value))
    }
    const url = `${base}${path}${search.size ? `?${search}` : ''}`
    const headers = new Headers(optionsForRequest.headers)
    headers.set('Accept', 'application/json')
    if (body !== undefined) headers.set('Content-Type', 'application/json')
    signal?.throwIfAborted()
    const token = await options.getAccessToken?.()
    signal?.throwIfAborted()
    if (token) headers.set('Authorization', `Bearer ${token}`)
    const serializedBody = body === undefined ? undefined : JSON.stringify(body)
    let response: Response
    try {
      response = await fetcher(url, {
        method, headers, body: serializedBody, signal,
        credentials: 'omit', cache: 'no-store', redirect: 'error',
      })
    } catch (error) {
      signal?.throwIfAborted()
      if (isAbortError(error)) throw error
      throw new ApiError('Unable to connect. Check your connection and try again.', {
        kind: 'network', method, code: 'network_error',
      })
    }
    signal?.throwIfAborted()
    const correlation = requestId(response.headers.get('X-Request-ID'))
    if (response.ok && response.status === 204) return undefined
    let data: unknown
    const mediaType = response.headers.get('Content-Type')?.split(';')[0].trim().toLowerCase()
    if (mediaType === 'application/json' || mediaType?.endsWith('+json')) {
      try {
        data = await response.json()
      } catch (error) {
        signal?.throwIfAborted()
        if (isAbortError(error)) throw error
        // Malformed bodies are handled below; never display raw proxy/server text.
      }
    }
    if (!response.ok) {
      const envelope = errorEnvelope(data) ? data.error : undefined
      throw new ApiError(envelope?.message ?? safeHttpMessage(response.status), {
        kind: 'http', method, status: response.status,
        code: envelope?.code ?? 'http_error',
        requestId: correlation ?? envelope?.request_id,
        details: envelope?.details,
        retryAfterMs: retryAfter(response.headers.get('Retry-After')),
      })
    }
    if (data === undefined) {
      throw new ApiError('The service returned an unexpected response. Please try again.', {
        kind: 'invalid_response', method, status: response.status,
        code: 'invalid_response', requestId: correlation,
      })
    }
    // Feature contracts supply T (or their own runtime decoder). This is not schema validation.
    return data as T
  }

  async function get<T>(path: ApiPath, requestOptions: Omit<RequestOptions, 'method' | 'body'> = {}): Promise<T> {
    const data = await request<T>(path, { ...requestOptions, method: 'GET' })
    if (data === undefined) {
      throw new ApiError('The service returned an unexpected response. Please try again.', {
        kind: 'invalid_response', method: 'GET', status: 204, code: 'invalid_response',
      })
    }
    return data
  }

  return { request, get }
}
