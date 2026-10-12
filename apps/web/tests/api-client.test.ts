import assert from 'node:assert/strict'
import { test } from 'node:test'
import { isCancelledError } from '@tanstack/react-query'
import { ApiError, createApiClient } from '../src/lib/api-client'
import type { ApiPath, CursorPage } from '../src/lib/api-types'
import { apiQueryKey, createQueryClient, queryRetryDelay, shouldRetryQuery } from '../src/lib/query-client'

const json = (body: unknown, status = 200, headers: HeadersInit = {}) =>
  new Response(JSON.stringify(body), { status, headers: { 'Content-Type': 'application/json', ...headers } })

test('GET encodes query values, uses current token and passes cancellation signal', async () => {
  let token = 'first-token'
  const calls: { url: string; options: RequestInit }[] = []
  const client = createApiClient({
    baseUrl: 'https://api.example.test/api/v1/',
    getAccessToken: async () => token,
    fetch: async (url, options) => {
      calls.push({ url: String(url), options: options! })
      return json({ items: [], next_cursor: null })
    },
  })
  const signal = new AbortController().signal
  const page = await client.get<CursorPage<unknown>>('/scheduling/appointments', {
    query: { cursor: 'a+/=?&', limit: 25, cancelled: false, omitted: null, absent: undefined }, signal,
  })
  assert.deepEqual(page, { items: [], next_cursor: null })
  const url = new URL(calls[0].url)
  assert.equal(url.pathname, '/api/v1/scheduling/appointments')
  assert.equal(url.searchParams.get('cursor'), 'a+/=?&')
  assert.equal(url.searchParams.get('limit'), '25')
  assert.equal(url.searchParams.get('cancelled'), 'false')
  assert.equal(url.searchParams.has('omitted'), false)
  const headers = new Headers(calls[0].options.headers)
  assert.equal(headers.get('Authorization'), 'Bearer first-token')
  assert.equal(headers.get('Accept'), 'application/json')
  assert.equal(headers.has('Content-Type'), false)
  assert.equal(calls[0].options.signal, signal)
  assert.equal(calls[0].options.credentials, 'omit')
  assert.equal(calls[0].options.cache, 'no-store')
  assert.equal(calls[0].options.redirect, 'error')
  token = 'refreshed-token'
  await client.get('/tenant/clinics')
  assert.equal(new Headers(calls[1].options.headers).get('Authorization'), 'Bearer refreshed-token')
})

test('JSON writes preserve body and custom headers; 204 needs no JSON parser', async () => {
  const client = createApiClient({ fetch: async (url, options) => {
    assert.equal(url, '/api/v1/tenant/clinics')
    assert.equal(options?.method, 'POST')
    assert.equal(options?.body, '{"name":"Synthetic clinic"}')
    assert.equal(new Headers(options?.headers).get('Content-Type'), 'application/json')
    assert.equal(new Headers(options?.headers).get('Idempotency-Key'), 'synthetic-key')
    return new Response(null, { status: 204 })
  } })
  assert.equal(await client.request<void>('/tenant/clinics', {
    method: 'POST', body: { name: 'Synthetic clinic' }, headers: { 'Idempotency-Key': 'synthetic-key' },
  }), undefined)
})

test('reject unsafe paths before reading a token or making a request', async () => {
  let called = false
  const client = createApiClient({ getAccessToken: () => { called = true; return 'secret' } })
  for (const path of ['//evil.test', 'https://evil.test', '/billing/../tenant', '/billing/%2e%2e/tenant',
    '/billing/%2f%2fevil.test', '/billing/\\evil.test', '/billing?x=1', '/billing#fragment', '/billing/%ZZ']) {
    await assert.rejects(client.request(path as ApiPath))
  }
  assert.equal(called, false)
  for (const baseUrl of ['//evil.test', 'relative', 'https://user:password@example.test/api/v1', '/api/v1?x=1']) {
    assert.throws(() => createApiClient({ baseUrl }))
  }
})

test('C01 errors retain status, code, field details, correlation and Retry-After', async () => {
  const client = createApiClient({ fetch: async () => json({ error: {
    code: 'validation_error', message: 'One or more fields are invalid.',
    request_id: 'body-reference', details: [{ field: 'query.limit', code: 'out_of_range', message: 'Use 1-100.' }],
  } }, 422, { 'X-Request-ID': 'header-reference', 'Retry-After': '3' }) })
  await assert.rejects(client.get('/tenant/clinics'), error => {
    assert.ok(error instanceof ApiError)
    assert.equal(error.status, 422)
    assert.equal(error.code, 'validation_error')
    assert.equal(error.requestId, 'header-reference')
    assert.equal(error.details[0].field, 'query.limit')
    assert.equal(error.retryAfterMs, 3000)
    assert.equal(shouldRetryQuery(0, error), false)
    return true
  })
})

test('nonconforming errors never expose raw proxy or FastAPI content', async () => {
  for (const response of [new Response('<html>SECRET database trace</html>', { status: 502 }),
    json({ detail: 'SECRET validation input' }, 422),
    json({ error: { message: 'SECRET incomplete envelope' } }, 500)]) {
    const client = createApiClient({ fetch: async () => response })
    await assert.rejects(client.get('/tenant/clinics'), error => {
      assert.ok(error instanceof ApiError)
      assert.equal(error.kind, 'http')
      assert.equal(error.message.includes('SECRET'), false)
      assert.deepEqual(error.details, [])
      return true
    })
  }
})

test('non-JSON and malformed JSON successes fail safely; JSON reads reject empty 204', async () => {
  for (const response of [new Response('<html>SPA fallback</html>', { status: 200 }),
    new Response('{broken', { headers: { 'Content-Type': 'application/json' } }),
    new Response(null, { status: 204 })]) {
    const client = createApiClient({ fetch: async () => response })
    await assert.rejects(client.get('/tenant/clinics'), error => error instanceof ApiError && error.kind === 'invalid_response')
  }
})

test('network failures are safe and AbortError is preserved', async () => {
  const client = createApiClient({ fetch: async () => { throw new TypeError('SECRET token in network URL') } })
  await assert.rejects(client.get('/tenant/clinics'), error => {
    assert.ok(error instanceof ApiError)
    assert.equal(error.kind, 'network')
    assert.equal(error.message.includes('SECRET'), false)
    return true
  })
  const abort = new DOMException('Cancelled', 'AbortError')
  const aborted = createApiClient({ fetch: async () => { throw abort } })
  await assert.rejects(aborted.get('/tenant/clinics'), error => error === abort)
  const controller = new AbortController()
  controller.abort()
  await assert.rejects(client.get('/tenant/clinics', { signal: controller.signal }), { name: 'AbortError' })
})

test('aborting while JSON is read stays cancellation, not a malformed-response error', async () => {
  const abort = new DOMException('Cancelled', 'AbortError')
  const response = json({})
  response.json = async () => { throw abort }
  const client = createApiClient({ fetch: async () => response })
  await assert.rejects(client.get('/tenant/clinics'), error => error === abort)
})

test('retry policy excludes auth, validation, mutation, cancellation and excessive waits', () => {
  for (const status of [400, 401, 403, 404, 409, 422]) {
    assert.equal(shouldRetryQuery(0, new ApiError('Safe', { kind: 'http', method: 'GET', code: 'http_error', status })), false)
  }
  const transient = new ApiError('Safe', { kind: 'http', method: 'GET', code: 'unavailable', status: 503, retryAfterMs: 3000 })
  assert.equal(shouldRetryQuery(0, transient), true)
  assert.equal(shouldRetryQuery(1, transient), true)
  assert.equal(shouldRetryQuery(2, transient), false)
  assert.equal(queryRetryDelay(0, transient), 3000)
  assert.equal(queryRetryDelay(1, new Error()), 2000)
  assert.equal(shouldRetryQuery(0, new ApiError('Safe', { kind: 'http', method: 'GET', code: 'rate_limited', status: 429, retryAfterMs: 60_000 })), false)
  assert.equal(shouldRetryQuery(0, new ApiError('Safe', { kind: 'network', method: 'POST', code: 'network_error' })), false)
  assert.equal(shouldRetryQuery(0, new DOMException('Cancelled', 'AbortError')), false)
})

test('query client bounds actual GET retries and never retries mutations', async () => {
  const queryClient = createQueryClient()
  let reads = 0
  let writes = 0
  const client = createApiClient({ fetch: async (_url, options) => {
    if (options?.method === 'GET') reads++
    else writes++
    return json({}, 503)
  } })
  try {
    await assert.rejects(queryClient.fetchQuery({ queryKey: ['read'], retryDelay: 0, queryFn: () => client.get('/tenant/clinics') }))
    assert.equal(reads, 3)
    const mutation = queryClient.getMutationCache().build(queryClient, {
      mutationFn: () => client.request('/tenant/clinics', { method: 'POST', body: {} }),
    })
    await assert.rejects(mutation.execute(undefined))
    assert.equal(writes, 1)
  } finally {
    queryClient.clear()
  }
})

test('cached query keys separate users, tenants, roles and filters', () => {
  const scope = { subject: 'user-a', tenantId: 'clinic-a', role: 'doctor' }
  const key = apiQueryKey(scope, 'scheduling', 'appointments', { cursor: 'page-a' })
  assert.notDeepEqual(key, apiQueryKey({ ...scope, subject: 'user-b' }, 'scheduling', 'appointments', { cursor: 'page-a' }))
  assert.notDeepEqual(key, apiQueryKey({ ...scope, tenantId: 'clinic-b' }, 'scheduling', 'appointments', { cursor: 'page-a' }))
  assert.notDeepEqual(key, apiQueryKey({ ...scope, role: 'patient' }, 'scheduling', 'appointments', { cursor: 'page-a' }))
  assert.notDeepEqual(key, apiQueryKey(scope, 'scheduling', 'appointments', { cursor: 'page-b' }))
  scope.subject = 'changed-user'
  assert.equal(key[1].subject, 'user-a')
})

test('query cancellation aborts its in-flight transport without retrying', async () => {
  const queryClient = createQueryClient()
  let started!: () => void
  const ready = new Promise<void>(resolve => { started = resolve })
  let calls = 0
  let aborted = false
  const client = createApiClient({ fetch: async (_url, options) => {
    calls++
    return new Promise<Response>((_resolve, reject) => {
      options?.signal?.addEventListener('abort', () => {
        aborted = true
        reject(new DOMException('Cancelled', 'AbortError'))
      }, { once: true })
      started()
    })
  } })
  try {
    const pending = queryClient.fetchQuery({
      queryKey: ['cancelled-read'],
      queryFn: ({ signal }) => client.get('/tenant/clinics', { signal }),
    })
    const rejected = assert.rejects(pending, error => isCancelledError(error))
    await ready
    await queryClient.cancelQueries()
    await rejected
    assert.equal(aborted, true)
    assert.equal(calls, 1)
  } finally {
    queryClient.clear()
  }
})
