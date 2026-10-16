import assert from 'node:assert/strict'
import { test } from 'node:test'
import { createElement } from 'react'
import { renderToStaticMarkup } from 'react-dom/server'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { parseRoute } from '../src/navigation/access'
import type { Identity } from '../src/features/clinics/api'

const values = new Map<string, string>()
const storage: Storage = {
  get length() { return values.size },
  clear: () => values.clear(),
  getItem: key => values.get(key) ?? null,
  key: index => [...values.keys()][index] ?? null,
  removeItem: key => { values.delete(key) },
  setItem: (key, value) => { values.set(key, value) },
}
Object.defineProperty(globalThis, 'sessionStorage', { value: storage, configurable: true })
Object.defineProperty(globalThis, 'location', { value: { origin: 'http://localhost:5173', pathname: '/', search: '' }, configurable: true })
const { AppShell } = await import('../src/navigation/AppShell')
const { StaffManagement } = await import('../src/features/staff/StaffManagement')
const clinicA = '11111111-1111-4111-8111-111111111111'
const clinicB = '22222222-2222-4222-8222-222222222222'
const identity: Identity = {
  subject_id: 'subject', global_roles: [],
  memberships: [{ tenant_id: clinicA, roles: ['clinic_admin'], status: 'active' }],
}

function render(client: QueryClient, path: string) {
  return renderToStaticMarkup(createElement(QueryClientProvider, { client },
    createElement(AppShell, {
      route: parseRoute(path), children: () => createElement('p', null, 'Protected feature mounted'),
    }),
  ))
}

test('shell gates feature mounting on sign-in and a successful current identity lookup', () => {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  const path = `/clinic-admin/clinics/${clinicA}/profile`
  try {
    values.clear()
    assert.match(render(client, path), /Sign in to access/)
    assert.doesNotMatch(render(client, path), /Protected feature mounted/)
    storage.setItem('telelink.session', JSON.stringify({ accessToken: 'test-token', refreshToken: 'test-refresh', expiresAt: Date.now() + 3600000 }))
    assert.match(render(client, path), /Checking your access/)
    assert.doesNotMatch(render(client, path), /Protected feature mounted/)
    client.setQueryData(['identity', 'test-token'], identity)
    assert.match(render(client, path), /Protected feature mounted/)
    assert.doesNotMatch(render(client, `/clinic-admin/clinics/${clinicB}/profile`), /Protected feature mounted/)
    assert.match(render(client, `/clinic-admin/clinics/${clinicB}/profile`), /You do not have access/)
    client.setQueryData(['identity', 'test-token'], { ...identity, memberships: [] })
    assert.doesNotMatch(render(client, path), /Protected feature mounted/)
    storage.clear()
    assert.doesNotMatch(render(client, path), /Protected feature mounted/)
  } finally { client.clear(); storage.clear() }
})

test('a failed access refresh blocks features even if old identity data remains', () => {
  const client = new QueryClient()
  try {
    storage.setItem('telelink.session', JSON.stringify({ accessToken: 'test-token', refreshToken: 'test-refresh', expiresAt: Date.now() + 3600000 }))
    client.setQueryData(['identity', 'test-token'], identity)
    client.getQueryCache().find({ queryKey: ['identity', 'test-token'] })!.setState({ status: 'error', error: new Error('Offline') })
    const markup = render(client, `/clinic-admin/clinics/${clinicA}/staff`)
    assert.match(markup, /Could not verify your access/)
    assert.doesNotMatch(markup, /Protected feature mounted/)
  } finally { client.clear(); storage.clear() }
})

test('staff page accepts email and renders readable account details', () => {
  const client = new QueryClient()
  try {
    storage.setItem('telelink.session', JSON.stringify({ accessToken: 'test-token', refreshToken: 'test-refresh', expiresAt: Date.now() + 3600000 }))
    client.setQueryData(['clinic-profile', 'test-token', clinicA], { name: 'Example Clinic' })
    client.setQueryData(['staff', 'test-token', clinicA], {
      pages: [{ items: [{ membership_id: 'member', subject_id: 'stable-account-id', tenant_id: clinicA, roles: ['doctor'], status: 'active', subject: { display_name: 'Dr Example', email: 'doctor@example.test' } }], next_cursor: null }],
      pageParams: [null],
    })
    const markup = renderToStaticMarkup(createElement(QueryClientProvider, { client }, createElement(StaffManagement, { tenantId: clinicA })))
    assert.match(markup, /type="email"/)
    assert.match(markup, /Dr Example/)
    assert.match(markup, /doctor@example.test/)
    assert.match(markup, /Example Clinic/)
    assert.doesNotMatch(markup, /Existing subject ID|stable-account-id/)
  } finally { client.clear(); storage.clear() }
})
