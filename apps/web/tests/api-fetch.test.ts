import assert from 'node:assert/strict'
import { test } from 'node:test'
import { apiFetch } from '../src/lib/api'
import { queryClient } from '../src/lib/query-client'

test('forwards fetch options and adds API base and token', async context => {
  const signal = new AbortController().signal
  const response = new Response('{"ok":true}')
  context.mock.method(globalThis, 'fetch', async (url: string, init: RequestInit) => {
    assert.equal(url, '/api/v1/tenant/clinics?limit=25')
    assert.equal(init.method, 'POST')
    assert.equal(init.body, '{"name":"Synthetic clinic"}')
    assert.equal(init.signal, signal)
    const headers = new Headers(init.headers)
    assert.equal(headers.get('Authorization'), 'Bearer test-token')
    assert.equal(headers.get('Content-Type'), 'application/json')
    assert.equal(init.credentials, 'omit')
    assert.equal(init.cache, 'no-store')
    assert.equal(init.redirect, 'error')
    return response
  })
  assert.equal(await apiFetch('/tenant/clinics?limit=25', {
    method: 'POST', accessToken: 'test-token', signal,
    headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ name: 'Synthetic clinic' }),
  }), response)
})

test('anonymous requests and 204 responses return the native Response', async context => {
  context.mock.method(globalThis, 'fetch', async (_url: string, init: RequestInit) => {
    assert.equal(new Headers(init.headers).has('Authorization'), false)
    return new Response(null, { status: 204 })
  })
  assert.equal((await apiFetch('/tenant/clinics', { method: 'DELETE' })).status, 204)
})

test('HTTP failures have a safe message and are not retried', async context => {
  const mockedFetch = context.mock.method(globalThis, 'fetch', async () =>
    new Response('SECRET server trace', { status: 503 }))
  await assert.rejects(apiFetch('/tenant/clinics'), { message: 'Request failed (HTTP 503).' })
  assert.equal(mockedFetch.mock.callCount(), 1)
  assert.equal(queryClient.getDefaultOptions().queries?.retry, false)
  assert.equal(queryClient.getDefaultOptions().mutations?.retry, false)
})

test('cancellation remains the native fetch error', async context => {
  const error = new DOMException('Cancelled', 'AbortError')
  context.mock.method(globalThis, 'fetch', async () => { throw error })
  await assert.rejects(apiFetch('/tenant/clinics'), caught => caught === error)
})

test('rejects alternate origins before attaching a token', async context => {
  const mockedFetch = context.mock.method(globalThis, 'fetch', async () => new Response())
  for (const path of ['https://other.test', '//other.test', '/\\other.test']) {
    await assert.rejects(apiFetch(path, { accessToken: 'test-token' }))
  }
  assert.equal(mockedFetch.mock.callCount(), 0)
})
