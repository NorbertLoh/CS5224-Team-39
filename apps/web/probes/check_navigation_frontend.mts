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

import {
  appointmentPaymentAttention,
  orderAttention,
  pendingAttention,
  verificationAttention,
} from '../src/navigation/attention'
import { navigationItems } from '../src/navigation/useNavigationAttention'

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
function render(
  path: string,
  identity = all,
  seed?: (client: QueryClient) => void,
) {
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
  seed?.(client)
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
// Attention follows current actionable states, never terminal history or another patient.
assert.equal(verificationAttention(null)?.tone, 'danger')
for (const status of ['rejected', 'revoked'] as const)
  assert.equal(verificationAttention({ status })?.label, 'Action needed')
assert.equal(verificationAttention({ status: 'pending' })?.tone, 'waiting')
assert.equal(verificationAttention({ status: 'approved' }), undefined)
assert.equal(pendingAttention(0, 'Reviews'), undefined)
assert.equal(pendingAttention(undefined, 'Reviews'), undefined)
assert.equal(pendingAttention(27, 'Reviews')?.count, 27)
const payable = {
  patient_id: a,
  status: 'pending_payment',
  payment_resolution: 'awaiting_payment',
  hold_expires_at: '2030-01-01T01:00:00Z',
  ends_at: '2030-01-01T02:00:00Z',
} as const
const now = Date.parse('2030-01-01T00:00:00Z')
assert.equal(
  appointmentPaymentAttention(
    [
      payable,
      { ...payable, patient_id: b },
      { ...payable, status: 'cancelled' },
      { ...payable, payment_resolution: 'refund_required' },
      { ...payable, hold_expires_at: '2029-01-01T00:00:00Z' },
    ],
    a,
    now,
  )?.count,
  1,
)
assert.equal(
  appointmentPaymentAttention([payable], a, Date.parse('2030-01-02T00:00:00Z')),
  undefined,
)
const unpaid = {
  patient_id: a,
  status: 'awaiting_payment',
  payment_status: 'unpaid',
} as const
const active = {
  ...unpaid,
  status: 'dispatched',
  payment_status: 'succeeded',
} as const
assert.equal(
  orderAttention([unpaid, { ...unpaid, patient_id: b }], a)?.count,
  1,
)
assert.equal(orderAttention([active], a)?.tone, 'waiting')
assert.equal(
  orderAttention([{ ...unpaid, payment_status: 'pending' }], a)?.tone,
  'waiting',
)
assert.equal(
  orderAttention(
    [
      { ...active, status: 'delivered' },
      { ...unpaid, payment_status: 'refunded' },
      { ...unpaid, status: 'cancelled' },
    ],
    a,
  ),
  undefined,
)
assert.equal(
  orderAttention([{ ...active, status: 'exception' }], a)?.tone,
  'danger',
)
assert.equal(
  orderAttention(
    [{ ...active, status: 'cancelled', payment_status: 'refund_required' }],
    a,
  )?.tone,
  'danger',
)
const pages: Array<string | null> = []
const paged = await navigationItems(async (cursor) => {
  pages.push(cursor)
  return cursor
    ? { items: [2], next_cursor: null }
    : { items: [1], next_cursor: 'page-2' }
})
assert.deepEqual(pages, [null, 'page-2'])
assert.deepEqual(paged, [1, 2])
await assert.rejects(
  navigationItems(async () => ({ items: [], next_cursor: 'repeated' })),
  /did not advance/,
)
const patientAttention = render('/patient', patient, (client) => {
  client.setQueryData(
    ['scheduling', 'navigation-attention', session.accessToken, a],
    [
      {
        ...payable,
        hold_expires_at: '2099-01-01T00:00:00Z',
        ends_at: '2099-01-01T01:00:00Z',
      },
    ],
  )
  client.setQueryData(
    ['fulfilment', 'navigation-attention', session.accessToken, a],
    [unpaid, active],
  )
})
assert(patientAttention.includes('Payment due'))
assert(patientAttention.includes('Needs attention'))
assert(patientAttention.includes('text-red-700'))
const platformAttention = render('/platform-admin/clinics', all, (client) => {
  const filters = { q: '', from: '', to: '', status: 'all' }
  client.setQueryData(
    ['platform-clinics', 'counts', session.accessToken, filters],
    { pending_review: 28 },
  )
  client.setQueryData(
    ['doctor-applications', 'counts', session.accessToken, filters],
    { pending: 13 },
  )
})
assert(platformAttention.includes('28'))
assert(platformAttention.includes('13'))
assert(platformAttention.includes('Pending'))
const needsVerification = render('/join-as-doctor', patient, (client) =>
  client.setQueryData(['doctor-application', session.accessToken], {
    status: 'revoked',
  }),
)
assert(needsVerification.includes('Action needed'))
const inReview = render('/join-as-doctor', patient, (client) =>
  client.setQueryData(['doctor-application', session.accessToken], {
    status: 'pending',
  }),
)
assert(inReview.includes('In review'))
assert(!inReview.includes('Action needed'))
const approved = render('/doctor', all, (client) =>
  client.setQueryData(['doctor-application', session.accessToken], {
    status: 'approved',
  }),
)
assert(!approved.includes('Action needed'))
values.delete('telelink.session')
const signedOut = render('/')
assert(!signedOut.includes('Switch workspace'))
assert(!signedOut.includes('<nav '))
console.log(
  'PASS: all-role workspace selection, patient-only switcher hidden, application-only access, one section bar, clinic context, revoked membership, platform exceptions, consultations signed-out/denied navigation, attention statuses, full pagination, patient scope and rendered badges.',
)
