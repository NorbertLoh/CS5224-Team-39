import assert from 'node:assert/strict'
import { test } from 'node:test'
import { createServer as httpServer } from 'node:http'
import type { AddressInfo } from 'node:net'
import { createServer } from 'vite'
import { schedulingClient } from './scheduling-helpers'
import { createCheckout, listPayments } from '../src/features/payments/api'

test('real Vite HTTP proxy strips billing prefix and blocks internal routes', async (context) => {
  const calls: { path: string; auth?: string; key?: string; body: string }[] =
    []
  const upstream = httpServer(async (request, response) => {
    let body = ''
    for await (const chunk of request) body += chunk
    calls.push({
      path: request.url!,
      auth: request.headers.authorization,
      key: request.headers['idempotency-key'] as string,
      body,
    })
    response.setHeader('Content-Type', 'application/json')
    response.end(JSON.stringify({ items: [], next_cursor: null }))
  })
  await new Promise<void>((resolve) => upstream.listen(0, '127.0.0.1', resolve))
  const previous = process.env.BILLING_API_TARGET
  process.env.BILLING_API_TARGET = `http://127.0.0.1:${(upstream.address() as AddressInfo).port}`
  const client = schedulingClient()
  let vite: Awaited<ReturnType<typeof createServer>> | undefined
  try {
    vite = await createServer({
      server: { host: '127.0.0.1', port: 0, open: false, watch: null },
      logLevel: 'error',
    })
    await vite.listen()
    const origin = `http://127.0.0.1:${(vite.httpServer!.address() as AddressInfo).port}`
    const nativeFetch = globalThis.fetch
    context.mock.method(
      globalThis,
      'fetch',
      (input: string, init?: RequestInit) =>
        nativeFetch(`${origin}${input}`, init),
    )
    await listPayments('tenant-a', 'consultation', 'pending', 'opaque+/=')
    await createCheckout('appointment-a', 'b07-stable-key')
    assert.equal(new URL(calls[0].path, origin).pathname, '/payments')
    assert.equal(
      new URL(calls[0].path, origin).searchParams.get('cursor'),
      'opaque+/=',
    )
    assert.equal(calls[0].auth, 'Bearer s07-test')
    assert.equal(calls[1].path, '/consultation-checkouts')
    assert.equal(calls[1].key, 'b07-stable-key')
    assert.deepEqual(JSON.parse(calls[1].body), {
      appointment_id: 'appointment-a',
    })
    for (const path of [
      '/api/v1/billing/internal/payments/x',
      '/api/v1/billing/internal?x=1',
      '/api/v1/billing/%69nternal/payments/x',
    ]) {
      assert.equal((await nativeFetch(`${origin}${path}`)).status, 404)
    }
    assert.equal(calls.length, 2, 'internal requests never reach the service')
  } finally {
    client.clear()
    await vite?.close()
    await new Promise<void>((resolve, reject) =>
      upstream.close((error) => (error ? reject(error) : resolve())),
    )
    if (previous === undefined) delete process.env.BILLING_API_TARGET
    else process.env.BILLING_API_TARGET = previous
  }
})
