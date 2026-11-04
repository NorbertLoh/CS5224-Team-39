import { readFileSync } from 'node:fs'
import { runInNewContext } from 'node:vm'
import assert from 'node:assert/strict'
import { test } from 'node:test'

const code = readFileSync(new URL('../service-route.js.tftpl', import.meta.url), 'utf8')
  .replace('${allowed_sources}', JSON.stringify(['203.0.113.10', '203.0.113.11']))
const handler = runInNewContext(`${code}; handler`)
const event = (uri, ip = '203.0.113.10') => ({ viewer: { ip }, request: { uri, method: 'POST', headers: { authorization: { value: 'service-credential' } }, querystring: { cursor: { value: 'page' } } } })

test('both NAT addresses reach every owner with credentials/query preserved', () => {
  for (const owner of ['identity', 'tenant', 'scheduling', 'consultation', 'clinical-records', 'billing', 'document', 'fulfilment']) {
    for (const ip of ['203.0.113.10', '203.0.113.11']) {
      const input = event(`/service/${owner}/internal/context`, ip)
      const output = handler(input)
      assert.equal(output.uri, `/api/v1/${owner}/internal/context`)
      assert.equal(output.headers.authorization.value, 'service-credential')
      assert.equal(output.querystring.cursor.value, 'page')
      assert.equal(output.method, 'POST')
    }
  }
})

test('public callers cannot spoof NAT access with a forwarded-IP header', () => {
  const input = event('/service/identity/internal/context', '198.51.100.15')
  input.request.headers['x-forwarded-for'] = { value: '203.0.113.10' }
  const output = handler(input)
  assert.equal(output.statusCode, 403)
  assert.equal(output.headers['cache-control'].value, 'no-store')
})

test('unknown owners, prefix confusion and ambiguous paths fail closed', () => {
  for (const path of ['/service/identity-other/x', '/service/unknown/x', '/api/v1/identity/internal/x', '/service/identity/../billing/x', '/service/identity/%2e%2e/x', '/service/identity/%252e/x', '/service/identity/a%2fb', '/service/identity/a\\b', '/service/identity/./x']) {
    assert.equal(handler(event(path)).statusCode, 403, path)
  }
})
