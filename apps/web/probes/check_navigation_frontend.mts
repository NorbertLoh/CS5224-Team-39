import assert from 'node:assert/strict'
import { createElement } from 'react'
import { renderToStaticMarkup } from 'react-dom/server'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import type { Identity } from '../src/auth/identity'
import { canAccess, parseRoute, type Role } from '../src/navigation/access'
import {
  availableWorkspaces,
  currentWorkspace,
  workspaceHref,
} from '../src/navigation/workspaces'

const a = '00000000-0000-4000-8000-000000000001'
const b = '00000000-0000-4000-8000-000000000002'
const revoked = '00000000-0000-4000-8000-000000000003'
const all: Identity = {
  subject_id: a,
  global_roles: ['patient', 'platform_admin'],
  memberships: [
    { tenant_id: a, roles: ['doctor', 'clinic_admin'], status: 'active' },
    { tenant_id: b, roles: ['clinic_admin'], status: 'active' },
    {
      tenant_id: revoked,
      roles: ['doctor', 'clinic_admin'],
      status: 'revoked',
    },
  ],
}
const patient: Identity = {
  subject_id: a,
  global_roles: ['patient'],
  memberships: [],
}
const platform: Identity = { ...patient, global_roles: ['platform_admin'] }
assert.deepEqual(availableWorkspaces(all), [
  'patient',
  'doctor',
  'clinic_admin',
  'platform_admin',
])
assert.deepEqual(
  availableWorkspaces({ ...patient, memberships: [all.memberships[2]] }),
  ['patient'],
)
for (const [path, role] of [
  ['/patient/documents', 'patient'],
  ['/doctor/availability', 'doctor'],
  ['/join-as-doctor', 'doctor'],
  ['/clinic-admin', 'clinic_admin'],
  ['/platform-admin/doctors', 'platform_admin'],
] as const)
  assert.equal(currentWorkspace(all, parseRoute(path)), role)
assert.equal(
  currentWorkspace(patient, parseRoute('/join-as-doctor')),
  'registration',
)
assert.equal(currentWorkspace(all, parseRoute('/')), 'patient')
assert.equal(currentWorkspace(all, parseRoute('/register-clinic')), undefined)
assert.equal(
  currentWorkspace(platform, parseRoute(`/clinic-admin/clinics/${a}/staff`)),
  'platform_admin',
)
assert.equal(
  canAccess(platform, parseRoute(`/clinic-admin/clinics/${a}/orders`)),
  false,
)
assert.equal(canAccess(patient, parseRoute('/doctor')), false)
assert.equal(
  workspaceHref(all, 'clinic_admin', parseRoute(`/doctor/clinics/${a}`)),
  `/clinic-admin/clinics/${a}/profile`,
)
assert.equal(
  workspaceHref(all, 'doctor', parseRoute(`/clinic-admin/clinics/${b}/staff`)),
  '/doctor',
)
assert.equal(
  workspaceHref(all, 'doctor', parseRoute('/join-as-doctor'), a),
  `/doctor/clinics/${a}`,
)
assert.equal(
  workspaceHref(all, 'doctor', parseRoute('/join-as-doctor'), revoked),
  '/doctor',
)

const values = new Map<string, string>()
const storage = {
  getItem: (key: string) => values.get(key) ?? null,
  removeItem: (key: string) => values.delete(key),
  setItem: (key: string, value: string) => values.set(key, value),
}
const session = {
  accessToken: 'navigation-test',
  refreshToken: 'fixture',
  expiresAt: Date.now() + 3600000,
}
values.set('telelink.session', JSON.stringify(session))
Object.assign(globalThis, {
  localStorage: storage,
  sessionStorage: storage,
  location: { pathname: '/', search: '', origin: 'http://localhost' },
  window: { location: { search: '' } },
})
// Import after installing storage/location: the auth module reads callback state on load.
const { AppShell } = await import('../src/navigation/AppShell')
function render(path: string, identity = all) {
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false, staleTime: Infinity } },
  })
  client.setQueryData(['identity', session.accessToken], identity)
  const ids = identity.memberships
    .filter((m) => m.status === 'active')
    .map((m) => m.tenant_id)
  for (const role of ['doctor', 'clinic_admin'] as const) {
    const clinics = identity.memberships
      .filter((m) => m.status === 'active' && m.roles.includes(role))
      .map((m) => m.tenant_id)
    client.setQueryData(
      ['clinic-names', session.accessToken, role === 'clinic_admin', clinics],
      new Map(ids.map((id) => [id, id === a ? 'Alpha Clinic' : 'Beta Clinic'])),
    )
  }
  const html = renderToStaticMarkup(
    createElement(
      QueryClientProvider,
      { client },
      createElement(AppShell, {
        route: parseRoute(path),
        children: () => createElement('main', null, 'FEATURE CONTENT'),
      }),
    ),
  )
  client.clear()
  return html
}
for (const [path, label] of [
  ['/patient', 'Patient care'],
  ['/doctor', 'Doctor workspace'],
  ['/clinic-admin', 'Clinic administration'],
  ['/platform-admin/clinics', 'Platform administration'],
] as const) {
  const html = render(path)
  assert(html.includes(`Switch workspace. Current: ${label}`))
  assert.equal((html.match(/<nav /g) ?? []).length, 1)
  assert.equal((html.match(/aria-current="page"/g) ?? []).length, 1)
  assert(!html.includes('Your roles'))
}
const single = render('/patient', patient)
assert(!single.includes('aria-haspopup="menu"'))
assert(!single.includes('Switch workspace'))
assert(single.includes('Patient workspace'))
const registration = render('/join-as-doctor', patient)
assert(!registration.includes('Switch workspace'))
assert(registration.includes('Application status'))
assert(!registration.includes('>Availability<'))
assert(!registration.includes('>Appointments<'))
for (const role of ['patient', 'doctor'] as const satisfies readonly Role[]) {
  const room = render(`/${role}/consultation`)
  assert(!room.includes('aria-current="page"'))
  assert(!room.includes('aria-label="Doctor clinic"'))
}
const scoped = render(`/clinic-admin/clinics/${a}/staff`)
assert.equal((scoped.match(/<nav /g) ?? []).length, 1)
assert(scoped.includes('aria-label="Administration clinic"'))
assert(scoped.includes('Alpha Clinic'))
assert(scoped.includes(`href="/clinic-admin/clinics/${a}/orders"`))
assert(!scoped.includes(revoked))
const platformStaff = render(`/clinic-admin/clinics/${a}/staff`, platform)
assert(platformStaff.includes('Back to platform clinics'))
assert(!platformStaff.includes(`href="/clinic-admin/clinics/${a}/orders"`))
assert(
  !platformStaff.includes(`href="/clinic-admin/clinics/${a}/appointments"`),
)
assert(!platformStaff.includes(`href="/clinic-admin/clinics/${a}/settings"`))
const denied = render('/doctor', patient)
assert(!denied.includes('FEATURE CONTENT'))
assert(denied.includes('You do not have access'))
values.delete('telelink.session')
const signedOut = render('/')
assert(!signedOut.includes('Switch workspace'))
assert(!signedOut.includes('<nav '))
console.log(
  'PASS: all-role workspace selection, patient-only switcher hidden, application-only access, one section bar, clinic context, revoked membership, platform exceptions, consultations and signed-out/denied navigation.',
)
